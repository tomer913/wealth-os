/**
 * Wealth OS — Israeli credit card scraper
 *
 * Credential loading (in priority order):
 *   1. CONNECTOR_ID set → fetch from backend /credentials/ endpoint (DB-backed)
 *   2. Fallback → read from environment variables (legacy / local testing)
 *
 * Uses @sergienko4/israeli-bank-scrapers (Camoufox fork).
 */

import { createScraper, CompanyTypes } from '@sergienko4/israeli-bank-scrapers';
import https from 'https';

const API_URL      = process.env.WEALTH_OS_API_URL;
const SCRAPER_TOKEN = process.env.SCRAPER_SECRET;
const PORTFOLIO_ID  = process.env.PORTFOLIO_ID;
const CONNECTOR_ID  = process.env.CONNECTOR_ID || '';

if (!API_URL || !SCRAPER_TOKEN || !PORTFOLIO_ID) {
  console.error('Missing required env vars: WEALTH_OS_API_URL, SCRAPER_SECRET, PORTFOLIO_ID');
  process.exit(1);
}

// ── Error type → human-readable message ───────────────────────────────────────

const ERROR_MESSAGES = {
  INVALID_PASSWORD: 'Wrong password — update credentials',
  CHANGE_PASSWORD:  'Password expired — reset at card company website',
  INVALID_OTP:      'OTP required — not supported in automated mode',
  ACCOUNT_BLOCKED:  'Account blocked — contact card company',
  TIMEOUT:          'Site timeout — will retry next run',
  WAF_BLOCKED:      'Blocked by security — Camoufox should handle this',
  GENERIC:          'Unknown error',
};

// ── Company type mapping ───────────────────────────────────────────────────────

const COMPANY_TYPES = {
  isracard:   CompanyTypes.Isracard,
  cal:        CompanyTypes.VisaCal,
  max:        CompanyTypes.Max,
  leumi_card: CompanyTypes.Leumi,
  amex:       CompanyTypes.Amex,
};

// ── Credential loading ─────────────────────────────────────────────────────────

async function fetchCredentials() {
  const response = await fetch(
    `${API_URL}/api/v1/connectors/${CONNECTOR_ID}/credentials/`,
    { headers: { 'X-Scraper-Token': SCRAPER_TOKEN } },
  );
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`Credentials API returned ${response.status}: ${body}`);
  }
  return response.json();
}

function buildCardsFromCredentials(creds) {
  if (!creds?.cards?.length) return [];

  const companyId = COMPANY_TYPES[creds.company];
  if (!companyId) {
    console.error(`Unknown company in credentials response: ${creds.company}`);
    return [];
  }

  // Isracard uses 'id' as the login field; all other companies use 'username'
  const userKey = creds.company === 'isracard' ? 'id' : 'username';

  return creds.cards
    .filter(card => card.username && card.password)
    .map(card => ({
      source: creds.company,
      companyId,
      enabled: true,
      credentials: {
        [userKey]: card.username,
        password: card.password,
        ...(card.card6      ? { card6Digits: card.card6 }       : {}),
        ...(card.national_id ? { nationalID: card.national_id } : {}),
      },
    }));
}

function buildCardsFromEnvVars() {
  const cards = [];

  // Isracard — multiple physical cards share one login but differ by card6
  const isracard_ok = !!(process.env.ISRACARD_USERNAME && process.env.ISRACARD_PASSWORD);
  const isracard_card6s = [
    process.env.ISRACARD_CARD6,
    process.env.ISRACARD_CARD6_2,
    process.env.ISRACARD_CARD6_3,
  ].filter(Boolean);

  if (isracard_ok && isracard_card6s.length > 0) {
    for (const card6 of isracard_card6s) {
      cards.push({
        source: 'isracard', companyId: CompanyTypes.Isracard, enabled: true,
        credentials: { id: process.env.ISRACARD_USERNAME, password: process.env.ISRACARD_PASSWORD, card6Digits: card6 },
      });
    }
  } else if (isracard_ok) {
    cards.push({
      source: 'isracard', companyId: CompanyTypes.Isracard, enabled: true,
      credentials: { id: process.env.ISRACARD_USERNAME, password: process.env.ISRACARD_PASSWORD },
    });
  }

  if (process.env.CAL_USERNAME && process.env.CAL_PASSWORD) {
    cards.push({ source: 'cal', companyId: CompanyTypes.VisaCal, enabled: true,
      credentials: { username: process.env.CAL_USERNAME, password: process.env.CAL_PASSWORD } });
  }
  if (process.env.MAX_USERNAME && process.env.MAX_PASSWORD) {
    cards.push({ source: 'max', companyId: CompanyTypes.Max, enabled: true,
      credentials: { username: process.env.MAX_USERNAME, password: process.env.MAX_PASSWORD } });
  }
  if (process.env.LEUMI_CARD_USERNAME && process.env.LEUMI_CARD_PASSWORD) {
    cards.push({ source: 'leumi_card', companyId: CompanyTypes.Leumi, enabled: true,
      credentials: { username: process.env.LEUMI_CARD_USERNAME, password: process.env.LEUMI_CARD_PASSWORD,
        nationalID: process.env.LEUMI_CARD_NATIONAL_ID } });
  }
  if (process.env.AMEX_USERNAME && process.env.AMEX_PASSWORD) {
    cards.push({ source: 'amex', companyId: CompanyTypes.Amex, enabled: true,
      credentials: { username: process.env.AMEX_USERNAME, password: process.env.AMEX_PASSWORD } });
  }

  return cards;
}

// ── Scrape one card entry ──────────────────────────────────────────────────────

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
      },
    );
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  console.log('=== Wealth OS Credit Card Scraper ===');

  let CARDS = [];

  if (CONNECTOR_ID) {
    console.log(`Fetching credentials for connector ${CONNECTOR_ID}...`);
    try {
      const creds = await fetchCredentials();
      CARDS = buildCardsFromCredentials(creds);
      console.log(`Loaded ${CARDS.length} card(s) from DB — company: ${creds?.company}`);
    } catch (err) {
      console.error('Failed to fetch credentials from API:', err.message);
      console.log('Falling back to env var credentials...');
      CARDS = buildCardsFromEnvVars();
    }
  } else {
    console.log('No CONNECTOR_ID set — using env var credentials (legacy mode)');
    CARDS = buildCardsFromEnvVars();
  }

  const active = CARDS.filter(c => c.enabled);

  if (active.length === 0) {
    console.log('No cards configured.');
    console.log('  New architecture: set CONNECTOR_ID and add cards via the Connectors UI.');
    console.log('  Legacy mode:      set credential env vars (ISRACARD_USERNAME etc.).');
    process.exit(0);
  }

  console.log(`Active cards: ${active.map(c =>
    `${c.source}${c.credentials.card6Digits ? `(${c.credentials.card6Digits})` : ''}`,
  ).join(', ')}`);

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
      summary.errors.push({ source: card.source, errorType: 'GENERIC', message: err.message });
    }
  }

  console.log(
    `\n=== Done: ${summary.created} created, ${summary.skipped} skipped, ${summary.errors.length} errors ===`,
  );

  if (summary.errors.length > 0) {
    console.log('Errors:');
    summary.errors.forEach(e => console.log(`  [${e.source}] ${e.errorType}: ${e.message}`));
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
