/**
 * Parser for the site's WhatsApp-style formatted text (ARCHITECTURE.md §6 "Formatted text";
 * contract schema `FormattedText`): `*bold*`, `_italic_`, `- ` bullets nested by two spaces, and
 * paragraphs separated by a blank line. Used by `<FormattedText>` in the CMS preview now and on
 * the public site in Phase 5.
 *
 * It returns a small tree of plain objects, never HTML. The renderer turns the tree into React
 * elements, so anything that looks like HTML ("<b>", "<script>") stays visible text.
 * SECURITY: there is no way to produce a link, an attribute or raw markup from this syntax
 * (SECURITY.md §5: raw HTML is never rendered). Keep it that way: links in content go through
 * block fields that the API validates (e.g. the CTA block), not through this text.
 *
 * How it works:
 *   1. Lines are split on "\n" ("\r\n" is normalised first).
 *   2. A line whose text starts with "- " after its indent is a bullet. Two spaces of indent are
 *      one level of nesting (a tab counts as two spaces). A jump of more than one level nests
 *      only one level deeper, so "- a" followed by "      - b" still reads sensibly.
 *   3. Other non-blank lines join the current paragraph; each newline inside a paragraph is kept
 *      as a line break, as in WhatsApp. A blank line ends the paragraph or list.
 *   4. Inline markers are matched per line (they never span lines), using WhatsApp's rules: an
 *      opening marker follows the start of the line, a space or punctuation and is followed by a
 *      non-space; the closing one follows a non-space and is followed by the end, a space or
 *      punctuation. The nearest valid closing marker wins. A marker with no partner, or inside a
 *      word (snake_case, 5*3*2), stays as typed. The text between two markers is then read the
 *      same way, as if it were a line of its own.
 *   5. PERF: parsing is linear in the text's length (see `parseChars`), because the API accepts
 *      50,000 characters and the CMS preview re-parses on every key press.
 */

/** A run of inline content: text, bold or italic (which may contain each other). */
export type InlineNode =
  | { type: "text"; text: string }
  | { type: "bold"; children: InlineNode[] }
  | { type: "italic"; children: InlineNode[] };

/** One bullet: its own text and, optionally, a nested list under it. */
export interface ListItemNode {
  children: InlineNode[];
  sublist: ListItemNode[];
}

export type BlockNode =
  /** A paragraph; each entry of `lines` is one line (shown with a line break between). */
  { type: "paragraph"; lines: InlineNode[][] } | { type: "list"; items: ListItemNode[] };

/** Deepest bullet level kept; deeper bullets are shown at this level. */
export const MAX_LIST_DEPTH = 4;

const MARKERS = new Set(["*", "_"]);
// Letters (any script, Devanagari included), their combining marks, and digits form words.
const WORD = /[\p{L}\p{M}\p{N}]/u;
const SPACE = /\s/u;

function isWordChar(char: string | undefined): boolean {
  return char !== undefined && WORD.test(char);
}

function isSpace(char: string | undefined): boolean {
  return char !== undefined && SPACE.test(char);
}

/**
 * Can the marker at `index` open, reading only the characters in [start, end)? The text between
 * an opening and a closing marker is read on its own, so its edges count as the edges of a line.
 */
function canOpen(chars: readonly string[], index: number, start: number, end: number): boolean {
  const before = index > start ? chars[index - 1] : undefined;
  const after = index + 1 < end ? chars[index + 1] : undefined;
  if (after === undefined || isSpace(after) || after === chars[index]) return false;
  return (
    before === undefined || isSpace(before) || (!isWordChar(before) && before !== chars[index])
  );
}

/** Can the marker at `index` close, reading only the characters before `end`? */
function canClose(chars: readonly string[], index: number, end: number): boolean {
  const before = chars[index - 1];
  const after = index + 1 < end ? chars[index + 1] : undefined;
  if (before === undefined || isSpace(before)) return false;
  return after === undefined || isSpace(after) || (!isWordChar(after) && after !== chars[index]);
}

/**
 * For each marker, `next[i]` is the first index at or after `i` holding that marker where it can
 * close when the whole line is read (-1 if none). One right-to-left pass per marker.
 */
function closerTables(chars: readonly string[]): Map<string, Int32Array> {
  const tables = new Map<string, Int32Array>();
  for (const marker of MARKERS) {
    const next = new Int32Array(chars.length + 1).fill(-1);
    for (let index = chars.length - 1; index >= 0; index -= 1) {
      const closes = chars[index] === marker && canClose(chars, index, chars.length);
      next[index] = closes ? index : (next[index + 1] as number);
    }
    tables.set(marker, next);
  }
  return tables;
}

/**
 * The nearest closing marker for the opener at `open`, inside a run that ends before `end`, or -1.
 *
 * WHY the table plus one extra check: inside a run, a marker can close exactly as it would on the
 * whole line, except the run's last character, whose right-hand neighbour (the run's own closing
 * marker) is out of view. So the nearest whole-line closer before `end - 1` is the answer;
 * failing that, the run's last character is checked on its own.
 */
function findClose(
  chars: readonly string[],
  tables: Map<string, Int32Array>,
  open: number,
  end: number,
): number {
  const marker = chars[open] as string;
  // WHY open + 2: the content between the markers must not be empty ("**" is not bold).
  const from = open + 2;
  if (from >= end) return -1;
  const nearest = (tables.get(marker) as Int32Array)[from] as number;
  if (nearest !== -1 && nearest < end - 1) return nearest;
  const last = end - 1;
  return chars[last] === marker && canClose(chars, last, end) ? last : -1;
}

function pushText(nodes: InlineNode[], text: string) {
  if (text === "") return;
  const last = nodes[nodes.length - 1];
  if (last?.type === "text") last.text += text;
  else nodes.push({ type: "text", text });
}

/** A bold or italic run being read: its children so far and where it ends. */
interface OpenRun {
  type: "bold" | "italic";
  start: number;
  end: number;
  nodes: InlineNode[];
  plain: string;
}

/**
 * Inline content of one line. Works on code points so emoji and Hindi are never split.
 *
 * PERF: linear in the line's length. The closer tables make each `findClose` O(1), every
 * character is read once, and open runs live on an explicit stack instead of the call stack, so
 * a 50,000-character line full of markers neither takes seconds (as the first, quadratic
 * version did; review M3) nor overflows the stack. formatted-text.test.tsx times it.
 */
function parseChars(chars: readonly string[]): InlineNode[] {
  const tables = closerTables(chars);
  const top: OpenRun = { type: "bold", start: 0, end: chars.length, nodes: [], plain: "" };
  const stack: OpenRun[] = [];
  let run = top;
  let index = 0;
  for (;;) {
    if (index >= run.end) {
      pushText(run.nodes, run.plain);
      const parent = stack.pop();
      if (parent === undefined) return top.nodes;
      parent.nodes.push({ type: run.type, children: run.nodes });
      index = run.end + 1; // step over the closing marker
      run = parent;
      continue;
    }
    const char = chars[index] as string;
    const opens = MARKERS.has(char) && canOpen(chars, index, run.start, run.end);
    const close = opens ? findClose(chars, tables, index, run.end) : -1;
    if (close === -1) {
      run.plain += char;
      index += 1;
      continue;
    }
    pushText(run.nodes, run.plain);
    run.plain = "";
    stack.push(run);
    const type = char === "*" ? "bold" : "italic";
    run = { type, start: index + 1, end: close, nodes: [], plain: "" };
    index += 1;
  }
}

/** Inline content of one line of text: `*bold*` and `_italic_`, everything else as text. */
export function parseInline(line: string): InlineNode[] {
  return parseChars([...line]);
}

interface BulletLine {
  depth: number;
  text: string;
}

/** The bullet on this line (depth from its indent), or null for an ordinary line. */
function bulletOf(line: string): BulletLine | null {
  // WHY \S: a lone "- " is shown as typed rather than as an empty bullet.
  const match = /^([ \t]*)- (.*\S.*)$/u.exec(line);
  if (!match) return null;
  const indent = (match[1] ?? "").replace(/\t/g, "  ").length;
  return { depth: Math.floor(indent / 2), text: (match[2] ?? "").trim() };
}

/** Builds the nested list from consecutive bullet lines. */
function buildList(bullets: readonly BulletLine[]): ListItemNode[] {
  const root: ListItemNode[] = [];
  // stack[d] is the list currently open at depth d.
  const stack: ListItemNode[][] = [root];
  for (const bullet of bullets) {
    // WHY clamp: a jump of several levels nests only one deeper than the open list.
    const depth = Math.min(bullet.depth, stack.length - 1, MAX_LIST_DEPTH - 1);
    stack.length = depth + 1;
    const item: ListItemNode = { children: parseInline(bullet.text), sublist: [] };
    (stack[depth] as ListItemNode[]).push(item);
    stack.push(item.sublist);
  }
  return root;
}

/** The whole text as paragraphs and (nested) lists. Empty or blank text gives an empty array. */
export function parseFormattedText(text: string): BlockNode[] {
  const blocks: BlockNode[] = [];
  let paragraph: string[] = [];
  let bullets: BulletLine[] = [];

  const flushParagraph = () => {
    if (paragraph.length > 0) {
      blocks.push({ type: "paragraph", lines: paragraph.map(parseInline) });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (bullets.length > 0) {
      blocks.push({ type: "list", items: buildList(bullets) });
      bullets = [];
    }
  };

  for (const line of text.replace(/\r\n?/g, "\n").split("\n")) {
    if (line.trim() === "") {
      flushParagraph();
      flushList();
      continue;
    }
    const bullet = bulletOf(line);
    if (bullet) {
      flushParagraph();
      bullets.push(bullet);
    } else {
      flushList();
      paragraph.push(line.trim());
    }
  }
  flushParagraph();
  flushList();
  return blocks;
}

function inlineToPlain(nodes: readonly InlineNode[]): string {
  return nodes
    .map((node) => (node.type === "text" ? node.text : inlineToPlain(node.children)))
    .join("");
}

function itemsToPlain(items: readonly ListItemNode[]): string[] {
  return items.flatMap((item) => [inlineToPlain(item.children), ...itemsToPlain(item.sublist)]);
}

/**
 * The text without formatting marks, paragraphs and bullets joined by spaces: for search
 * previews, excerpts and character counts of what a visitor actually reads.
 */
export function formattedTextToPlain(text: string): string {
  return parseFormattedText(text)
    .flatMap((block) =>
      block.type === "paragraph" ? block.lines.map(inlineToPlain) : itemsToPlain(block.items),
    )
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}
