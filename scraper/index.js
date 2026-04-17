/**
 * Wealth OS — Israeli credit card scraper
 *
 * Uses israeli-bank-scrapers (https://github.com/eshaham/israeli-bank-scrapers)
 * to scrape credit card transactions and post them to the Wealth OS ingest endpoint.
 *
 * Credentials are read from environment variables (set as GitHub Actions secrets).
 * Each card type is only scraped if its credentials are present.
 *
 * Supported sources:
 *   isracard   — ISRACARD_USERNAME, ISRACARD_PASSWORD, ISRACARD_CARD6
 *   cal        — CAL_USERNAME, CAL_PASSWORD
 *   max        — MAX_USERNAME, MAX_PASSWORD
 *   leumi_card — LEUMI_CARD_USERNAME, LEUMI_CARD_PASSWORD, LEUMI_CARD_NATIONAL_ID
 *   amex       — AMEX_USERNAME, AMEX_PASSWORD
 */

import { createScraper, CompanyTypes } from 'israeli-bank-scrapers';
import puppeteer from 'puppeteer';
import https from 'https';

const API_URL = process.env.WEALTH_OS_API_URL;
const SCRAPER_TOKEN = process.env.SCRAPER_SECRET;
const PORTFOLIO_ID = process.env.PORTFOLIO_ID;

if (!API_URL || !SCRAPER_TOKEN || !PORTFOLIO_ID) {
  console.error('Missing required env vars: WEALTH_OS_API_URL, SCRAPER_SECRET, PORTFOLIO_ID');
  process.exit(1);
}

// ── Card configurations ────────────────────────────────────────────────────────

const CARDS = [
  {
    source: 'isracard',
    companyId: CompanyTypes.isracard,
    enabled: !!(process.env.ISRACARD_USERNAME && process.env.ISRACARD_PASSWORD),
    credentials: {
      id: process.env.ISRACARD_USERNAME,
      password: process.env.ISRACARD_PASSWORD,
      card6Digits: process.env.ISRACARD_CARD6,
    },
  },
  {
    source: 'cal',
    companyId: CompanyTypes.cal,
    enabled: !!(process.env.CAL_USERNAME && process.env.CAL_PASSWORD),
    credentials: {
      username: process.env.CAL_USERNAME,
      password: process.env.CAL_PASSWORD,
    },
  },
  {
    source: 'max',
    companyId: CompanyTypes.max,
    enabled: !!(process.env.MAX_USERNAME && process.env.MAX_PASSWORD),
    credentials: {
      username: process.env.MAX_USERNAME,
      password: process.env.MAX_PASSWORD,
    },
  },
  {
    source: 'leumi_card',
    companyId: CompanyTypes.leumiCard,
    enabled: !!(process.env.LEUMI_CARD_USERNAME && process.env.LEUMI_CARD_PASSWORD),
    credentials: {
      username: process.env.LEUMI_CARD_USERNAME,
      password: process.env.LEUMI_CARD_PASSWORD,
      nationalID: process.env.LEUMI_CARD_NATIONAL_ID,
    },
  },
  {
    source: 'amex',
    companyId: CompanyTypes.amex,
    enabled: !!(process.env.AMEX_USERNAME && process.env.AMEX_PASSWORD),
    credentials: {
      username: process.env.AMEX_USERNAME,
      password: process.env.AMEX_PASSWORD,
    },
  },
];

// ── Main ──────────────────────────────────────────────────────────────────────

async function scrapeCard(card) {
  console.log(`\n[${card.source}] Starting scrape...`);

  const browser = await puppeteer.launch({
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
    ],
  });

  const scraper = createScraper({
    companyId: card.companyId,
    startDate: new Date(new Date().setDate(new Date().getDate() - 90)), // last 90 days
    combineInstallments: false,
    showBrowser: false,
    browser,
    skipCloseBrowser: false,
  });

  const result = await scraper.scrape(card.credentials);

  if (!result.success) {
    console.error(`[${card.source}] Scrape failed:`, result.errorType, result.errorMessage);
    return { source: card.source, count: 0, error: result.errorMessage };
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
        },
      });
    }
  }

  console.log(`[${card.source}] Found ${txns.length} transactions`);
  return { source: card.source, transactions: txns };
}

async function postToIngest(source, transactions) {
  const body = JSON.stringify({
    source,
    portfolio_id: PORTFOLIO_ID,
    transactions,
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
          resolve(JSON.parse(data));
        });
      }
    );
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

async function main() {
  console.log('=== Wealth OS Credit Card Scraper ===');
  const active = CARDS.filter((c) => c.enabled);
  console.log(`Active cards: ${active.map((c) => c.source).join(', ') || 'none'}`);

  if (active.length === 0) {
    console.log('No cards configured — set credential env vars to enable scraping');
    process.exit(0);
  }

  let totalCreated = 0;
  let totalSkipped = 0;

  for (const card of active) {
    try {
      const scraped = await scrapeCard(card);
      if (scraped.error || !scraped.transactions?.length) continue;

      const result = await postToIngest(scraped.source, scraped.transactions);
      totalCreated += result.created || 0;
      totalSkipped += result.skipped || 0;
    } catch (err) {
      console.error(`[${card.source}] Error:`, err.message);
    }
  }

  console.log(`\n=== Done: ${totalCreated} created, ${totalSkipped} skipped ===`);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
