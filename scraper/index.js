/**
 * Wealth OS — Israeli credit card scraper
 *
 * Uses @sergienko4/israeli-bank-scrapers (Camoufox fork) to scrape credit card
 * transactions and post them to the Wealth OS ingest endpoint.
 *
 * Credentials are read from environment variables (set as GitHub Actions secrets).
 * TARGET_COMPANY filters to a single company when set (used by the per-company
 * connector scheduler). If empty, all configured companies are scraped.
 *
 * Isracard supports multiple physical cards via numbered CARD6 secrets:
 *   ISRACARD_CARD6, ISRACARD_CARD6_2, ISRACARD_CARD6_3
 */

import { createScraper, CompanyTypes } from '@sergienko4/israeli-bank-scrapers';
import https from 'https';

const API_URL = process.env.WEALTH_OS_API_URL;
const SCRAPER_TOKEN = process.env.SCRAPER_SECRET;
const PORTFOLIO_ID = process.env.PORTFOLIO_ID;
const TARGET_COMPANY = process.env.TARGET_COMPANY || '';

if (!API_URL || !SCRAPER_TOKEN || !PORTFOLIO_ID) {
  console.error('Missing required env vars: WEALTH_OS_API_URL, SCRAPER_SECRET, PORTFOLIO_ID');
  process.exit(1);
}

// ── Error type → human-readable message ───────────────────────────────────────

const ERROR_MESSAGES = {
  INVALID_PASSWORD:   'Wrong password — update credentials',
  CHANGE_PASSWORD:    'Password expired — reset at card company website',
  INVALID_OTP:        'OTP required — not supported in automated mode',
  ACCOUNT_BLOCKED:    'Account blocked — contact card company',
  TIMEOUT:            'Site timeout — will retry next run',
  WAF_BLOCKED:        'Blocked by security — Camoufox should handle this',
  GENERIC:            'Unknown error',
};

// ── Card configurations ────────────────────────────────────────────────────────
// Each entry in CARDS represents one scrape session (one set of credentials).
// Isracard is special: multiple physical cards share one login but differ by card6.

const CARDS = [];

// Isracard — build one entry per configured CARD6
const isracard_creds_ok = !!(process.env.ISRACARD_USERNAME && process.env.ISRACARD_PASSWORD);
const isracard_card6s = [
  process.env.ISRACARD_CARD6,
  process.env.ISRACARD_CARD6_2,
  process.env.ISRACARD_CARD6_3,
].filter(Boolean);

if (isracard_creds_ok && isracard_card6s.length > 0) {
  for (const card6 of isracard_card6s) {
    CARDS.push({
      source: 'isracard',
      companyId: CompanyTypes.Isracard,
      enabled: true,
      credentials: {
        id: process.env.ISRACARD_USERNAME,
        password: process.env.ISRACARD_PASSWORD,
        card6Digits: card6,
      },
    });
  }
} else if (isracard_creds_ok) {
  // Credentials set but no card6 — scrape without card6 filter
  CARDS.push({
    source: 'isracard',
    companyId: CompanyTypes.Isracard,
    enabled: true,
    credentials: {
      id: process.env.ISRACARD_USERNAME,
      password: process.env.ISRACARD_PASSWORD,
    },
  });
}

// Cal
if (process.env.CAL_USERNAME && process.env.CAL_PASSWORD) {
  CARDS.push({
    source: 'cal',
    companyId: CompanyTypes.VisaCal,
    enabled: true,
    credentials: {
      username: process.env.CAL_USERNAME,
      password: process.env.CAL_PASSWORD,
    },
  });
}

// Max
if (process.env.MAX_USERNAME && process.env.MAX_PASSWORD) {
  CARDS.push({
    source: 'max',
    companyId: CompanyTypes.Max,
    enabled: true,
    credentials: {
      username: process.env.MAX_USERNAME,
      password: process.env.MAX_PASSWORD,
    },
  });
}

// Leumi Card
if (process.env.LEUMI_CARD_USERNAME && process.env.LEUMI_CARD_PASSWORD) {
  CARDS.push({
    source: 'leumi_card',
    companyId: CompanyTypes.Leumi,
    enabled: true,
    credentials: {
      username: process.env.LEUMI_CARD_USERNAME,
      password: process.env.LEUMI_CARD_PASSWORD,
      nationalID: process.env.LEUMI_CARD_NATIONAL_ID,
    },
  });
}

// Amex
if (process.env.AMEX_USERNAME && process.env.AMEX_PASSWORD) {
  CARDS.push({
    source: 'amex',
    companyId: CompanyTypes.Amex,
    enabled: true,
    credentials: {
      username: process.env.AMEX_USERNAME,
      password: process.env.AMEX_PASSWORD,
    },
  });
}

// ── Scrape one card ────────────────────────────────────────────────────────────

async function scrapeCard(card) {
  console.log(`\n[${card.source}] Starting scrape...`);
  const scraper = createScraper({
    companyId: card.companyId,
    startDate: new Date(new Date().setDate(new Date().getDate() - 90)), // last 90 days
  });

  const result = await scraper.scrape(card.credentials);

  if (!result.success) {
    const message = ERROR_MESSAGES[result.errorType] || result.errorMessage || ERROR_MESSAGES.GENERIC;
    console.error(`[${card.source}] Scrape failed: ${result.errorType} — ${message}`);
    return { source: card.source, error: { errorType: result.errorType, message } };
  }

  // Flatten all accounts' transactions
  const txns = [];
  for (const account of result.accounts || []) {
    for (const tx of account.txns || []) {
      txns.push({
        date: tx.date,
        description: tx.description || '',
        amount: tx.chargedAmount || tx.originalAmount || 0,
        currency: tx.originalCurrency || 'ILS',
        identifier: tx.identifier || `${card.source}-${tx.date}-${tx.description}-${tx.chargedAmount}`,
        extra_data: {
          status: tx.status,
          type: tx.type,
          memo: tx.memo,
          category: tx.category,
          account_number: account.accountNumber,
          card6: card.credentials.card6Digits,
        },
      });
    }
  }

  console.log(`[${card.source}] Found ${txns.length} transactions`);
  return { source: card.source, transactions: txns };
}

// ── POST to backend ingest endpoint ───────────────────────────────────────────

async function postToIngest(source, transactions, error = null) {
  const body = JSON.stringify({
    source,
    portfolio_id: PORTFOLIO_ID,
    transactions: transactions || [],
    ...(error ? { error } : {}),
  });

  const url = new URL(`${API_URL}/api/v1/connectors/ingest/`);

  return new Promise((resolve, reject) => {
    const req = https.request(
      {
        hostname: url.hostname,
        port: url.port || 443,
        path: url.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(body),
          'X-Scraper-Token': SCRAPER_TOKEN,
        },
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => { data += chunk; });
        res.on('end', () => {
          console.log(`[${source}] Ingest response ${res.statusCode}:`, data);
          try { resolve(JSON.parse(data)); } catch { resolve({}); }
        });
      }
    );
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  console.log('=== Wealth OS Credit Card Scraper ===');
  if (TARGET_COMPANY) {
    console.log(`Target company: ${TARGET_COMPANY}`);
  }

  // Filter by TARGET_COMPANY if set; keep only enabled cards
  const active = CARDS.filter(
    (c) => c.enabled && (!TARGET_COMPANY || c.source === TARGET_COMPANY)
  );

  console.log(`Active cards: ${active.map((c) => `${c.source}${c.credentials.card6Digits ? `(${c.credentials.card6Digits})` : ''}`).join(', ') || 'none'}`);

  if (active.length === 0) {
    console.log('No cards configured — set credential env vars to enable scraping');
    process.exit(0);
  }

  const summary = { created: 0, skipped: 0, errors: [] };

  for (const card of active) {
    try {
      const scraped = await scrapeCard(card);

      if (scraped.error) {
        await postToIngest(scraped.source, [], scraped.error);
        summary.errors.push({ source: scraped.source, ...scraped.error });
        continue;
      }

      if (!scraped.transactions?.length) continue;

      const result = await postToIngest(scraped.source, scraped.transactions);
      summary.created += result.created || 0;
      summary.skipped += result.skipped || 0;
    } catch (err) {
      console.error(`[${card.source}] Unexpected error:`, err.message);
      summary.errors.push({
        source: card.source,
        errorType: 'GENERIC',
        message: err.message,
      });
    }
  }

  console.log(
    `\n=== Done: ${summary.created} created, ${summary.skipped} skipped, ${summary.errors.length} errors ===`
  );

  if (summary.errors.length > 0) {
    console.log('Errors:');
    summary.errors.forEach((e) =>
      console.log(`  [${e.source}] ${e.errorType}: ${e.message}`)
    );
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
