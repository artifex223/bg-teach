'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { launch } = require('browser-kit');

const args = process.argv.slice(2);
if (args.length < 2) {
  console.error('Usage: browser-run tests/verify_html.js <compiled.html> <shared.html>');
  process.exit(1);
}

const COMPILED_PATH = path.resolve(args[0]);
const SHARED_PATH = path.resolve(args[1]);
for (const p of [COMPILED_PATH, SHARED_PATH]) {
  if (!fs.existsSync(p)) {
    console.error(`Missing HTML file: ${p}`);
    process.exit(1);
  }
}

const COMPILED_URL = pathToFileURL(COMPILED_PATH).href;
const SHARED_URL = pathToFileURL(SHARED_PATH).href;

let failures = 0;
function check(name, ok, extra = '') {
  if (!ok) failures++;
  console.log((ok ? 'PASS' : 'FAIL') + ' | ' + name + (extra ? ' | ' + extra : ''));
}

function verifyThemeContrastAndZeroHex(html) {
  const m = html.match(/\[data-theme="dim"\]\s*\{([^}]*)\}/);
  if (!m) {
    check('dim theme block exists', false);
    return;
  }
  const vars = {};
  for (const d of m[1].matchAll(/--([a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    vars[d[1]] = d[2].trim();
  }
  const lin = (c) => {
    c /= 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const hex = (h) => {
    h = h.replace('#', '');
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  };
  const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  const ratio = (a, b) => {
    const [x, y] = [lum(hex(a)), lum(hex(b))].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  };
  const chk = (fg, bg, min) => {
    const r = ratio(vars[fg], vars[bg]);
    check(`dim contrast ${fg} on ${bg}`, r >= min, `${r.toFixed(2)} >= ${min}`);
  };
  for (const s of ['bg', 'surface-1', 'surface-2']) {
    chk('text', s, 7.0);
    chk('text-muted', s, 4.5);
    chk('text-faint', s, 3.0);
  }
  chk('text-on-accent', 'accent', 4.5);
  for (const s of ['ok', 'warn', 'bad', 'info']) chk(s, 'surface-1', 4.5);

  // Zero literal hex colors in component/layout CSS outside theme token blocks
  const styleMatch = html.match(/<style>([\s\S]*?)<\/style>/);
  if (!styleMatch) {
    check('style tag exists', false);
    return;
  }
  const withoutThemes = styleMatch[1]
    .replace(/:root\s*,\s*\[data-theme="felt"\]\s*\{[^}]*\}/g, '')
    .replace(/\[data-theme="ledger"\]\s*\{[^}]*\}/g, '')
    .replace(/\[data-theme="dim"\]\s*\{[^}]*\}/g, '');
  const hexMatches = withoutThemes.match(/#[0-9a-fA-F]{3,8}\b/g) || [];
  check('zero literal hex colors outside theme blocks', hexMatches.length === 0, hexMatches.join(', '));
  check('prototype switcher chrome stripped', !html.includes('#proto-switcher') && !html.includes('ps-bar') && !html.includes('?variant='));
}

async function checkViewportAndTargets(page, label, width, height) {
  await page.setViewportSize({ width, height });
  await page.waitForTimeout(40);
  const overflow = await page.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth,
    innerW: window.innerWidth,
  }));
  check(
    `no horizontal overflow (${label} @ ${width}x${height})`,
    overflow.scrollW <= overflow.innerW,
    `scrollW=${overflow.scrollW} innerW=${overflow.innerW}`
  );

  if (width === 390) {
    const badTargets = await page.evaluate(() => {
      const sel = 'button, a[href], input, select, summary, [role="button"], [role="tab"], [role="radio"], label.check-row';
      const out = [];
      for (const el of document.querySelectorAll(sel)) {
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') continue;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) continue;
        if (rect.height < 43.5 || rect.width < 43.5) {
          out.push({
            tag: el.tagName.toLowerCase(),
            text: (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 35),
            w: Math.round(rect.width),
            h: Math.round(rect.height),
          });
        }
      }
      return out;
    });
    check(
      `tap targets >= 44px (${label} @ 390x844)`,
      badTargets.length === 0,
      badTargets.length ? JSON.stringify(badTargets.slice(0, 5)) : 'all >= 44px'
    );
  }
}

(async () => {
  const html = fs.readFileSync(COMPILED_PATH, 'utf8');
  verifyThemeContrastAndZeroHex(html);

  const browser = await launch();
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const errors = [];
  const externalRequests = [];
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('request', (req) => {
    const url = req.url();
    if (!url.startsWith('file://') && !url.startsWith('data:') && !url.startsWith('blob:')) {
      externalRequests.push(url);
    }
  });

  try {
    await page.goto(COMPILED_URL, { waitUntil: 'load' });
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: 'load' });

    // 1. Rail hygiene & mandatory Variant C components
    const stageBtnCount = await page.locator('.vc-rail .vc-stage-btn').count();
    const hasTitle = (await page.locator('.vc-rail .vc-title').textContent()) === 'Lantern Harbor';
    const hasDraft = (await page.locator('.vc-rail .badge--draft').textContent()) === 'DRAFT';
    const hasDrawerBtn = (await page.locator('.vc-rail [data-action="toggle-c-drawer"]').count()) === 1;
    const hasPassBtn = (await page.locator('.vc-rail [data-action="toggle-c-passaround"]').count()) === 1;
    const railPlayersHidden = (await page.locator('.vc-rail [data-action="set-players"]').count()) === 0;
    const railThemeHidden = (await page.locator('.vc-rail [data-action="set-theme"]').count()) === 0;
    const railWakeHidden = (await page.locator('.vc-rail [data-action="toggle-wake"]').count()) === 0;
    check(
      'Variant C rail structure & rail hygiene',
      stageBtnCount === 5 && hasTitle && hasDraft && hasDrawerBtn && hasPassBtn && railPlayersHidden && railThemeHidden && railWakeHidden,
      `stages=${stageBtnCount}`
    );

    // 2. Viewports & tap targets across Stages 1-5 and open drawer (empty and populated)
    for (const [w, h] of [[390, 844], [1024, 768], [1280, 800]]) {
      for (const s of [1, 2, 3, 4, 5]) {
        await page.click(`[data-action="set-c-stage"][data-stage="${s}"]`);
        await checkViewportAndTargets(page, `stage${s}`, w, h);
      }
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.click('[data-action="toggle-c-drawer"]');
    await checkViewportAndTargets(page, 'drawer-open', 390, 844);
    await page.fill('#c-search', 'Lantern');
    await checkViewportAndTargets(page, 'drawer-with-results', 390, 844);
    await page.click('[data-action="clear-c-search"]');
    await page.click('.va-drawer [data-action="toggle-c-drawer"]');

    // 3. Stages 1, 3, 4 content, inline SVGs, and Next navigation CTAs
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.click('[data-action="set-c-stage"][data-stage="1"]');
    const s1Text = await page.textContent('.vc-canvas');
    check(
      'Stage 1 renders HOLD UP cue and pitch_aloud',
      s1Text.includes('HOLD UP') && s1Text.includes('rival harbor wardens')
    );
    await page.click('.vc-canvas [data-action="set-c-stage"][data-stage="2"]');
    const flowSvgBox = await page.locator('.diagram-frame svg').first().boundingBox();
    check(
      'Next CTA advances Stage 1 -> Stage 2 and inline SVG turn-flow renders',
      (await page.getAttribute('.vc-stage-btn[aria-current="step"]', 'data-stage')) === '2' &&
        Boolean(flowSvgBox && flowSvgBox.width > 100 && flowSvgBox.height > 40),
      JSON.stringify(flowSvgBox)
    );

    await page.click('.vc-canvas [data-action="set-c-stage"][data-stage="3"]');
    const s3Text = await page.textContent('.vc-canvas');
    const s3ErrataCount = await page.locator('.vc-canvas .callout--errata').count();
    check(
      'Stage 3 renders phases, HOLD UP cues, subactions, free_action Bonus, and cargo errata callout',
      (await page.getAttribute('.vc-stage-btn[aria-current="step"]', 'data-stage')) === '3' &&
        s3Text.includes('HOLD UP: Hold up: Wooden Sloop') &&
        s3Text.includes('Light a Lantern:') &&
        s3Text.includes('Free Bonus Action') &&
        s3ErrataCount === 1 &&
        s3Text.includes('Cargo Hold Overflow Timing')
    );

    await page.click('.vc-canvas [data-action="set-c-stage"][data-stage="4"]');
    const s4Text = await page.textContent('.vc-canvas');
    const iconCount = await page.locator('.icon-glyph svg').count();
    const iconBox = await page.locator('.icon-glyph svg').first().boundingBox();
    check(
      'Stage 4 renders Beats 1-4 and iconography SVG glyphs',
      (await page.getAttribute('.vc-stage-btn[aria-current="step"]', 'data-stage')) === '4' &&
        s4Text.includes('Beat 1') &&
        s4Text.includes('Beat 4') &&
        iconCount === 6 &&
        Boolean(iconBox && iconBox.width > 10 && iconBox.height > 10),
      `count=${iconCount}`
    );
    await page.click('.vc-canvas [data-action="set-c-stage"][data-stage="5"]');
    check(
      'Stage 4 Next CTA advances to Stage 5',
      (await page.getAttribute('.vc-stage-btn[aria-current="step"]', 'data-stage')) === '5'
    );

    // 4. Player pills dynamically update setup deltas, win trigger, and 5P verify badge
    await page.click('[data-action="toggle-c-drawer"]');
    await page.click('.va-drawer [data-action="set-players"][data-players="2"]');
    await page.click('.va-drawer [data-action="toggle-c-drawer"]');
    await page.click('[data-action="set-c-stage"][data-stage="1"]');
    const s1_2p = await page.textContent('.vc-canvas');
    await page.click('[data-action="set-c-stage"][data-stage="2"]');
    const s2_2p = await page.textContent('.vc-canvas');
    const verifyBadge2P = await page.locator('label.check-row .badge--verify').count();

    await page.click('[data-action="toggle-c-drawer"]');
    await page.click('.va-drawer [data-action="set-players"][data-players="5"]');
    await page.click('.va-drawer [data-action="toggle-c-drawer"]');
    await page.click('[data-action="set-c-stage"][data-stage="1"]');
    const s1_5p = await page.textContent('.vc-canvas');
    await page.click('[data-action="set-c-stage"][data-stage="2"]');
    const s2_5p = await page.textContent('.vc-canvas');
    const verifyBadge5P = await page.locator('label.check-row .badge--verify').count();
    const s2ErrataCount = await page.locator('.vc-canvas .callout--errata').count();
    const s2DiffStrike = await page.locator('.vc-canvas .diff-strike').count();
    const s2DiffNew = await page.locator('.vc-canvas .diff-new').count();
    const s2VerifyCallout = await page.locator('.vc-canvas .callout--verify').count();

    check(
      'Player pills update setup deltas, win trigger, and conditional 5P verify badge',
      s1_2p.includes('6 completed Charters') &&
        s1_5p.includes('4 completed Charters') &&
        s2_2p.includes('14 cards') &&
        s2_2p.includes('10 Lanterns') &&
        s2_5p.includes('20 cards') &&
        s2_5p.includes('7 Lanterns') &&
        verifyBadge2P === 0 &&
        verifyBadge5P === 1 &&
        s2ErrataCount >= 1 &&
        s2DiffStrike >= 1 &&
        s2DiffNew >= 1 &&
        s2VerifyCallout >= 1
    );

    // 5. Setup checkboxes, players, and theme persist across reload via localStorage and clear on Reset
    await page.click('[data-action="toggle-c-drawer"]');
    await page.click('.va-drawer [data-action="set-theme"][data-theme-val="dim"]');
    await page.click('.va-drawer [data-action="toggle-c-drawer"]');
    const checkboxes = page.locator('input[data-action="toggle-check"]');
    await checkboxes.nth(0).check();
    await checkboxes.nth(1).check();
    const setupText2 = await page.textContent('.vc-rail');
    const storedRaw = await page.evaluate(() => localStorage.getItem('bg-teach:v1:proto-lantern-harbor-001'));
    await page.reload({ waitUntil: 'load' });
    const setupAfterReload = await page.textContent('.vc-rail');
    const playersAfterReload = await page.textContent('.vc-canvas');
    const themeAfterReload = await page.evaluate(() => document.documentElement.dataset.theme);
    await page.click('[data-action="set-c-stage"][data-stage="2"]');
    const stillChecked = await page.locator('input[data-action="toggle-check"]').nth(0).isChecked();
    await page.click('.vc-canvas [data-action="reset-setup"]');
    const setupAfterReset = await page.textContent('.vc-rail');
    check(
      'Setup checkboxes, players, and theme persist via localStorage and Reset clears setup',
      setupText2.includes('Setup (2/9)') &&
        Boolean(storedRaw && JSON.parse(storedRaw).checked.length === 2) &&
        setupAfterReload.includes('Setup (2/9)') &&
        playersAfterReload.includes('5P Active') &&
        themeAfterReload === 'dim' &&
        stillChecked &&
        setupAfterReset.includes('Setup (0/9)'),
      `${setupText2.match(/Setup \(\d+\/\d+\)/)?.[0]} -> ${setupAfterReset.match(/Setup \(\d+\/\d+\)/)?.[0]}`
    );

    // 6. Theme switching cycles felt -> ledger -> dim cleanly
    await page.click('[data-action="toggle-c-drawer"]');
    await page.click('.va-drawer [data-action="set-theme"][data-theme-val="felt"]');
    const bgFelt = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    await page.click('.va-drawer [data-action="set-theme"][data-theme-val="ledger"]');
    const themeLedger = await page.evaluate(() => document.documentElement.dataset.theme);
    const bgLedger = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    await page.click('.va-drawer [data-action="set-theme"][data-theme-val="dim"]');
    const themeDim = await page.evaluate(() => document.documentElement.dataset.theme);
    const bgDim = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    check(
      'Theme switcher cycles felt -> ledger -> dim cleanly',
      themeLedger === 'ledger' && themeDim === 'dim' && bgFelt !== bgLedger && bgLedger !== bgDim,
      `${bgFelt} / ${bgLedger} / ${bgDim}`
    );

    // 7. Drawer search filters, jumps to Stage 2, and Clear resets search
    await page.fill('#c-search', 'Winter Gale');
    const searchHits = await page.textContent('#c-search-results');
    await page.click('[data-action="c-jump-stage"][data-stage="2"]');
    const drawerClosedAfterJump = !(await page.locator('.va-drawer').isVisible());
    const activeStageAfterJump = await page.getAttribute('.vc-stage-btn[aria-current="step"]', 'data-stage');
    await page.click('[data-action="toggle-c-drawer"]');
    await page.click('[data-action="clear-c-search"]');
    const searchValCleared = await page.inputValue('#c-search');
    await page.click('.va-drawer [data-action="toggle-c-drawer"]');
    check(
      'Drawer search filters, jumps to Stage 2, and clears',
      searchHits.includes('Winter Gale') && drawerClosedAfterJump && activeStageAfterJump === '2' && searchValCleared === ''
    );

    // 8. Stage 5 renders Top Gotchas, Owner notes.md, Verify Before Table, Local PDF, and CC BY-SA
    await page.click('[data-action="set-c-stage"][data-stage="5"]');
    const stage5Text = await page.textContent('.vc-canvas');
    const localPdfCount = await page.locator('a.link-btn', { hasText: 'Local PDF' }).count();
    check(
      'Stage 5 renders gotchas, owner notes, verify, local PDF, and CC BY-SA',
      stage5Text.includes('Top First-Game Gotchas') &&
        stage5Text.includes('Verify Before Table') &&
        stage5Text.includes('Owner lantern-harbor.notes.md') &&
        stage5Text.includes('House Rulings:') &&
        stage5Text.includes('Source Precedence & CC BY-SA') &&
        stage5Text.includes('HarborWarden') &&
        localPdfCount >= 1
    );

    // 9. Pass-Around strips teacher-only content from BOTH canvas and drawer search, keeps player aid & attribution
    await page.click('[data-action="toggle-c-passaround"]');
    for (const [w, h] of [[390, 844], [1024, 768], [1280, 800]]) {
      await checkViewportAndTargets(page, 'pass-around', w, h);
    }
    const passCanvas = await page.textContent('.vc-shell--passaround');
    const passCanvasOk =
      !passCanvas.includes('Verify Before Table') &&
      !passCanvas.includes('DRAFT') &&
      !passCanvas.includes('HOLD UP') &&
      !passCanvas.includes('lantern-harbor.notes.md') &&
      !passCanvas.includes('House Rulings:') &&
      !passCanvas.includes('rival harbor wardens') &&
      passCanvas.includes('Win Trigger') &&
      passCanvas.includes('Your Turn in 3 Steps') &&
      passCanvas.includes('Iconography Key') &&
      passCanvas.includes('End-Game Scoring') &&
      passCanvas.includes('Important Table Errata') &&
      passCanvas.includes('Source Precedence & CC BY-SA');

    await page.click('[data-action="toggle-c-drawer"]');
    const queryNoCards = async (q) => {
      await page.fill('#c-search', q);
      const cards = await page.locator('#c-search-results .vd-card').count();
      const txt = await page.textContent('#c-search-results');
      return { cards, txt };
    };
    const qVerify = await queryNoCards('Auxiliary Pier');
    const qNotes = await queryNoCards('House Rulings');
    const qStage4 = await queryNoCards('Open-Handed Demo');
    const qPitch = await queryNoCards('rival harbor wardens');
    const qSetup = await queryNoCards('Calm Bay side face up');
    const qHoldUp = await queryNoCards('Wooden Sloop + 1 Silver coin');
    const qSayAloud = await queryNoCards('always free to sail through');
    const qErrata = await queryNoCards('Winter Gale');
    const jumpBtnsInPassAround = await page.locator('#c-search-results [data-action="c-jump-stage"]').count();
    await page.click('.va-drawer [data-action="toggle-c-drawer"]');
    check(
      'Pass-Around strips teacher-only content from canvas & drawer search while keeping table aid',
      passCanvasOk &&
        qVerify.cards === 0 && !qVerify.txt.includes('5P Auxiliary Pier') &&
        qNotes.cards === 0 && !qNotes.txt.includes('Treat only the single') &&
        qStage4.cards === 0 && !qStage4.txt.includes('Seat 1') &&
        qPitch.cards === 0 && !qPitch.txt.includes('coastal fog') &&
        qSetup.cards === 0 && !qSetup.txt.includes('Blocked Piers') &&
        qHoldUp.cards === 0 && !qHoldUp.txt.includes('Sail Your Sloop') &&
        qSayAloud.cards === 0 && !qSayAloud.txt.includes('connected water channels') &&
        qErrata.cards >= 1 && qErrata.txt.includes('Winter Gale') &&
        jumpBtnsInPassAround === 0
    );

    await page.click('[data-action="toggle-c-passaround"]');
    const restoredText = await page.textContent('#app-root');
    check(
      'Exiting Pass-Around restores teacher mode cleanly',
      restoredText.includes('Verify Before Table') && restoredText.includes('DRAFT')
    );

    // 10. Wake Lock toggle inside drawer transitions cleanly from Wake: Off
    await page.click('[data-action="toggle-c-drawer"]');
    const wakeBefore = await page.textContent('.va-drawer [data-action="toggle-wake"]');
    await page.click('.va-drawer [data-action="toggle-wake"]');
    await page.waitForTimeout(50);
    const wakeText = await page.textContent('.va-drawer [data-action="toggle-wake"]');
    check(
      'Wake Lock toggle transitions gracefully from Wake: Off',
      wakeBefore === 'Wake: Off' && (wakeText === 'Wake: On' || wakeText === 'Wake: N/A'),
      `${wakeBefore} -> ${wakeText}`
    );

    // 11. Shared build omits Local PDF while keeping Official PDF and BGG Search links
    await page.goto(SHARED_URL, { waitUntil: 'load' });
    const sharedLocalLinks = await page.locator('a.link-btn', { hasText: 'Local PDF' }).count();
    const sharedOfficialLinks = await page.locator('a.link-btn', { hasText: 'Official Publisher PDF' }).count();
    const sharedBggLinks = await page.locator('a.link-btn', { hasText: 'Search BGG Rules Forum' }).count();
    check(
      'Shared build omits Local PDF while keeping Official PDF & BGG Search',
      sharedLocalLinks === 0 && sharedOfficialLinks >= 1 && sharedBggLinks >= 1,
      `local=${sharedLocalLinks} official=${sharedOfficialLinks} bgg=${sharedBggLinks}`
    );

    // 12. Manual JSON-paste fallback, invalid JSON handling, dynamic bg-teach-v1 variants, and XSS/mXSS hardening
    const tplPath = path.resolve(__dirname, '../assets/template.html');
    const fixturePath = path.resolve(__dirname, '../tests/fixtures/lantern-harbor.guide.json');
    if (!fs.existsSync(tplPath) || !fs.existsSync(fixturePath)) {
      check('Template and fixture exist for manual paste & variant checks', false);
    } else {
      await page.goto(pathToFileURL(tplPath).href, { waitUntil: 'load' });
      const hasPasteBox = (await page.locator('#manual-guide-json').count()) === 1;
      await page.fill('#manual-guide-json', '{bad json');
      await page.click('[data-action="load-manual-json"]');
      const parseErrMsg = await page.textContent('#manual-json-error');
      await page.fill('#manual-guide-json', '{"schema_version":"bg-teach-v1","meta":{"title":"Incomplete"}}');
      await page.click('[data-action="load-manual-json"]');
      const shapeErrMsg = await page.textContent('#manual-json-error');

      // Synthetic 1-3P verified minimal guide with adversarial SVG/link payloads and long physical_cue
      const minimalGuide = {
        schema_version: 'bg-teach-v1',
        status: 'verified',
        bgg_id: null,
        game_uuid: null,
        meta: {
          title: 'Solo Pocket Test',
          subtitle: 'Minimal Verified Variant',
          publisher: 'Test Press',
          weight: 1.5,
          min_players: 1,
          max_players: 3,
          playtime_min: 20,
          teach_time_min: 3
        },
        links: {
          official_pdf_url: 'javascript:alert(1)',
          official_pdf_label: 'Unsafe JS Link',
          pdf_local_path: './local-book.pdf',
          pdf_local_label: 'Local PDF',
          bgg_search_url: 'https://boardgamegeek.com/geeksearch.php?action=search&objecttype=boardgame&q=Solo',
          bgg_search_label: 'Search BGG Rules Forum (Browser Only)'
        },
        stage1_hook: {
          title: 'Hook',
          physical_cue: 'Hold the solo deck',
          pitch_aloud: 'Survive three rounds.',
          win_summary: 'Score 10+ points.',
          win_trigger_by_players: { '1': 'Survive 1P.', '2': 'Reach 10 points (2P).', '3': 'Reach 8 points (3P).' },
          citations: ['(Rulebook p. 1)']
        },
        stage2_setup: {
          shared_board: [
            { id: 's1', name: 'Deck', deltas: { '1': 'Deal 5 cards.', '2': 'Deal 6 cards.', '3': 'Deal 7 cards.' }, citations: ['(Rulebook p. 2)'] }
          ],
          per_player: []
        },
        stage3_turn: {
          summary: 'Play one card.',
          turn_flow_svg:
            '<svg viewBox="0 0 240 80" onload="window.__xss=1"><title><p><![CDATA[</title><img src=x onerror="window.__xss=2">]]></p></title><desc>Minimal flow</desc><script>window.__xss=3</script><a href="javascript:alert(1)"><set attributeName="x" to="1"/></a><rect x="4" y="4" width="200" height="60" fill="var(--surface-2)"/></svg>',
          phases: [
            { id: 'p1', step: 1, name: 'Play Card', physical_cue: 'Tap deck', say_aloud: 'Draw and resolve.', player_summary: 'Draw 1 card.', citations: ['(Rulebook p. 3)'] }
          ],
          free_action: null
        },
        stage4_first_round: [
          {
            beat: 1,
            title: 'Opening Beat',
            physical_cue: 'Hold up the extra-long component card and stack of wooden cubes cleanly',
            say_aloud: 'Play one card face up.',
            citations: ['(Rulebook p. 4)']
          }
        ],
        stage5_reference: {
          edge_cases: [{ id: 'e1', title: 'Empty Deck', detail: 'Reshuffle discard once.', citations: ['(Rulebook p. 5)'] }],
          errata_list: [],
          verify_before_table: [],
          owner_notes: null,
          iconography: [{ id: 'i1', name: 'Cube', effect: 'Worth 1 VP.', citations: ['(Rulebook p. 6)'] }],
          scoring: { rows: [{ source: 'Cubes', points: '1 VP', citations: ['(Rulebook p. 6)'] }], tiebreakers: 'Shared win.' },
          precedence: 'Publisher Errata / Living Rulebook > Printed Rulebook',
          cc_by_sa: []
        }
      };

      await page.fill('#manual-guide-json', JSON.stringify(minimalGuide));
      await page.click('[data-action="load-manual-json"]');
      const minTitle = await page.locator('.vc-rail .vc-title').textContent();
      const draftCount = await page.locator('.badge--draft').count();
      const jsLinkCount = await page.locator('a[href^="javascript:"]').count();
      const unsafeSvgNodes = await page.evaluate(() => document.querySelectorAll('.diagram-frame script, .diagram-frame img, .diagram-frame set').length);
      const xssTriggered = await page.evaluate(() => Boolean(window.__xss));

      await page.setViewportSize({ width: 390, height: 844 });
      await page.click('[data-action="set-c-stage"][data-stage="4"]');
      await checkViewportAndTargets(page, 'minimal-long-badge-stage4', 390, 844);
      const fallbackIconSvg = await page.locator('.icon-glyph svg').count();

      await page.click('[data-action="toggle-c-drawer"]');
      const pillTexts = await page.locator('.va-drawer [data-action="set-players"]').allTextContents();
      await page.click('.va-drawer [data-action="toggle-c-drawer"]');

      await page.click('[data-action="set-c-stage"][data-stage="3"]');
      const s3Minimal = await page.textContent('.vc-canvas');
      await page.click('[data-action="set-c-stage"][data-stage="5"]');
      const s5Minimal = await page.textContent('.vc-canvas');

      await page.click('[data-action="toggle-c-passaround"]');
      const passMinimal = await page.textContent('.vc-shell--passaround');

      check(
        'Manual paste handles errors, dynamic 1-3P verified minimal variant, fallback icon, and SVG/link XSS hardening',
        hasPasteBox &&
          parseErrMsg.includes('Invalid guide JSON') &&
          shapeErrMsg.includes('Invalid guide JSON') &&
          minTitle === 'Solo Pocket Test' &&
          draftCount === 0 &&
          jsLinkCount === 0 &&
          unsafeSvgNodes === 0 &&
          !xssTriggered &&
          fallbackIconSvg === 1 &&
          pillTexts.join(',') === '1P,2P,3P' &&
          !s3Minimal.includes('Bonus') &&
          !s5Minimal.includes('Top First-Game Gotchas') &&
          !s5Minimal.includes('Verify Before Table') &&
          !s5Minimal.includes('Deterministic Local Addendum') &&
          !passMinimal.includes('Free Bonus') &&
          !passMinimal.includes('Important Table Errata')
      );
    }

    check('Zero console/page errors', errors.length === 0, errors.join(' | '));
    check('Zero external network requests', externalRequests.length === 0, externalRequests.join(' | '));
  } finally {
    await browser.close();
  }

  console.log(failures ? `\nSUMMARY: ${failures} FAIL` : '\nSUMMARY: ALL PASS');
  process.exit(failures ? 1 : 0);
})().catch((e) => {
  console.error('VERIFICATION SCRIPT ERROR', e);
  process.exit(1);
});
