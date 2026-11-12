// The formatted-text parser and renderer (ARCHITECTURE.md §6 "Formatted text"), and the CMS
// editor around it. SECURITY.md §5: anything that looks like HTML must come out as visible text.
import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  FormattedText,
  FormattedTextEditor,
  formattedTextToPlain,
  lengthText,
  parseFormattedText,
  parseInline,
} from "../src";

afterEach(cleanup);

describe("parseInline", () => {
  it("reads bold and italic", () => {
    expect(parseInline("a *bold* and _italic_ word")).toEqual([
      { type: "text", text: "a " },
      { type: "bold", children: [{ type: "text", text: "bold" }] },
      { type: "text", text: " and " },
      { type: "italic", children: [{ type: "text", text: "italic" }] },
      { type: "text", text: " word" },
    ]);
  });

  it("reads Markdown's **bold** as bold, and leaves other star runs as typed", () => {
    expect(parseInline("This is **sample content** here")).toEqual([
      { type: "text", text: "This is " },
      { type: "bold", children: [{ type: "text", text: "sample content" }] },
      { type: "text", text: " here" },
    ]);
    expect(parseInline("a ***b*** c")).toEqual([{ type: "text", text: "a ***b*** c" }]);
    expect(parseInline("2 ** 3")).toEqual([{ type: "text", text: "2 ** 3" }]);
    expect(parseInline("**unclosed")).toEqual([{ type: "text", text: "**unclosed" }]);
  });

  it("nests italic inside bold and bold inside italic", () => {
    expect(parseInline("*very _important_ note*")).toEqual([
      {
        type: "bold",
        children: [
          { type: "text", text: "very " },
          { type: "italic", children: [{ type: "text", text: "important" }] },
          { type: "text", text: " note" },
        ],
      },
    ]);
    expect(parseInline("_*both*_")).toEqual([
      { type: "italic", children: [{ type: "bold", children: [{ type: "text", text: "both" }] }] },
    ]);
  });

  it("allows punctuation around markers", () => {
    expect(parseInline("(*Note*): read this.")).toEqual([
      { type: "text", text: "(" },
      { type: "bold", children: [{ type: "text", text: "Note" }] },
      { type: "text", text: "): read this." },
    ]);
  });

  it.each([
    ["an opening marker with no partner", "*bold without end"],
    ["a closing marker with no partner", "end without start*"],
    ["a marker followed by a space", "price * 2 * 3"],
    ["markers inside a word", "snake_case_name and 5*3*2"],
    ["empty markers", "** and __"],
    ["a lone underscore", "_"],
  ])("leaves %s as typed", (_, text) => {
    expect(parseInline(text)).toEqual([{ type: "text", text }]);
  });

  it("keeps an unbalanced marker as text and still reads a later pair", () => {
    expect(parseInline("5 * 3 is *fifteen*")).toEqual([
      { type: "text", text: "5 * 3 is " },
      { type: "bold", children: [{ type: "text", text: "fifteen" }] },
    ]);
  });

  it("does not let markers cross: the nearest closing marker wins", () => {
    expect(parseInline("*a _b* c_")).toEqual([
      { type: "bold", children: [{ type: "text", text: "a _b" }] },
      { type: "text", text: " c_" },
    ]);
  });

  it("reads the text between two markers as a line of its own", () => {
    // The inner "*" before the closing one can close because its right-hand neighbour (the
    // outer closing marker) is out of view; the linear parser keeps this first-version rule.
    expect(parseInline("*x *y**")).toEqual([
      {
        type: "bold",
        children: [
          { type: "text", text: "x " },
          { type: "bold", children: [{ type: "text", text: "y" }] },
        ],
      },
    ]);
    expect(parseInline("*a **")).toEqual([
      { type: "bold", children: [{ type: "text", text: "a *" }] },
    ]);
  });

  it("works with Hindi, including vowel signs next to a marker", () => {
    expect(parseInline("*नमस्ते* दोस्तों")).toEqual([
      { type: "bold", children: [{ type: "text", text: "नमस्ते" }] },
      { type: "text", text: " दोस्तों" },
    ]);
    // The underscore follows a letter, so it is part of the word, not a marker.
    expect(parseInline("शब्द_एक_")).toEqual([{ type: "text", text: "शब्द_एक_" }]);
  });
});

describe("parseFormattedText", () => {
  it("splits paragraphs on blank lines and keeps single line breaks", () => {
    expect(parseFormattedText("Line one\nLine two\n\n  \nSecond paragraph")).toEqual([
      {
        type: "paragraph",
        lines: [[{ type: "text", text: "Line one" }], [{ type: "text", text: "Line two" }]],
      },
      { type: "paragraph", lines: [[{ type: "text", text: "Second paragraph" }]] },
    ]);
  });

  it("treats Windows line endings like Unix ones", () => {
    expect(parseFormattedText("a\r\n\r\nb")).toHaveLength(2);
  });

  it("returns nothing for empty or blank text", () => {
    expect(parseFormattedText("")).toEqual([]);
    expect(parseFormattedText(" \n\t\n ")).toEqual([]);
  });

  it("builds bullets nested by two spaces", () => {
    const [list] = parseFormattedText(
      "- Tower A\n  - 2 BHK\n  - 3 BHK\n    - Corner units\n- Tower B",
    );
    expect(list?.type).toBe("list");
    if (list?.type !== "list") return;
    expect(list.items).toHaveLength(2);
    expect(list.items[0]?.sublist.map((item) => item.children)).toEqual([
      [{ type: "text", text: "2 BHK" }],
      [{ type: "text", text: "3 BHK" }],
    ]);
    expect(list.items[0]?.sublist[1]?.sublist[0]?.children).toEqual([
      { type: "text", text: "Corner units" },
    ]);
    expect(list.items[1]?.sublist).toEqual([]);
  });

  it("nests only one level deeper when the indent jumps", () => {
    const [list] = parseFormattedText("- top\n      - jumped");
    if (list?.type !== "list") throw new Error("expected a list");
    expect(list.items[0]?.sublist[0]?.children).toEqual([{ type: "text", text: "jumped" }]);
  });

  it("caps nesting at four levels", () => {
    const text = ["- 1", "  - 2", "    - 3", "      - 4", "        - 5"].join("\n");
    const [list] = parseFormattedText(text);
    if (list?.type !== "list") throw new Error("expected a list");
    const level4 = list.items[0]?.sublist[0]?.sublist[0]?.sublist;
    expect(level4?.map((item) => item.children)).toEqual([
      [{ type: "text", text: "4" }],
      [{ type: "text", text: "5" }],
    ]);
  });

  it("counts a tab as two spaces of indent", () => {
    const [list] = parseFormattedText("- top\n\t- under");
    if (list?.type !== "list") throw new Error("expected a list");
    expect(list.items[0]?.sublist).toHaveLength(1);
  });

  it("ends a list at an ordinary line and starts a paragraph", () => {
    const blocks = parseFormattedText("Includes:\n- Parking\n- Clubhouse\nAsk for details.");
    expect(blocks.map((block) => block.type)).toEqual(["paragraph", "list", "paragraph"]);
  });

  it("needs a space after the dash, and text after it", () => {
    expect(parseFormattedText("-5% is not a bullet\n- ").map((b) => b.type)).toEqual(["paragraph"]);
  });

  it("reads markers inside bullets", () => {
    const [list] = parseFormattedText("- *Possession:* [month year]");
    if (list?.type !== "list") throw new Error("expected a list");
    expect(list.items[0]?.children[0]).toEqual({
      type: "bold",
      children: [{ type: "text", text: "Possession:" }],
    });
  });
});

// PERF (review M3): the API accepts 50,000 characters in a rich_text block or a post body, and
// the CMS preview re-parses on every key press. The first parser was quadratic (about 3 s for
// one line like "*a *a *a …"); this one is linear. The budget is generous for slow CI machines.
describe("parser performance", () => {
  const BUDGET_MS = 100;

  it.each([
    ["openers with no closer", "*a ".repeat(16_666)],
    ["italic openers with no closer", "_a ".repeat(16_666)],
    ["both markers mixed", "*a _a ".repeat(8_333)],
    ["many closed pairs", "*a* _b_ ".repeat(6_250)],
    ["lone markers", "* ".repeat(25_000)],
  ])("parses 50,000 characters of %s in well under 100 ms", (_, text) => {
    parseFormattedText(text.slice(0, 2_000)); // warm up the JIT so the timing is fair
    const started = performance.now();
    const blocks = parseFormattedText(text);
    const elapsedMs = performance.now() - started;
    expect(blocks).toHaveLength(1);
    expect(elapsedMs).toBeLessThan(BUDGET_MS);
  });

  it("handles thousands of nested runs without overflowing the stack", () => {
    const nested = parseInline(`${"*a ".repeat(8_000)}${"*".repeat(8_000)}`);
    let depth = 0;
    let node = nested[0];
    while (node && node.type !== "text") {
      depth += 1;
      node = node.children[node.children.length - 1];
    }
    expect(depth).toBe(7_999);
  });
});

describe("formattedTextToPlain", () => {
  it("drops the marks and joins the pieces", () => {
    expect(formattedTextToPlain("*Hello* _there_\n\n- one\n  - two")).toBe("Hello there one two");
  });

  it("drops Markdown's double stars too", () => {
    expect(formattedTextToPlain("This is **sample content** here")).toBe(
      "This is sample content here",
    );
  });
});

describe("FormattedText", () => {
  it("renders paragraphs, line breaks, bold, italic and nested lists", () => {
    const { container } = render(
      <FormattedText text={"*Bold* and _italic_\nnext line\n\n- a\n  - b"} />,
    );
    expect(container.querySelector("strong")?.textContent).toBe("Bold");
    expect(container.querySelector("em")?.textContent).toBe("italic");
    expect(container.querySelectorAll("p br")).toHaveLength(1);
    expect(container.querySelectorAll("ul ul li")).toHaveLength(1);
    expect(screen.getByText("b").tagName).toBe("LI");
  });

  it("shows HTML-looking text as text and creates no elements from it", () => {
    const text =
      '<script>alert("x")</script>\n\n*<img src=x onerror=alert(1)>* <b>not bold</b> <a href="javascript:alert(1)">link</a>';
    const { container } = render(<FormattedText text={text} />);
    expect(container.querySelector("script, img, b, a, iframe")).toBeNull();
    expect(container.textContent).toContain('<script>alert("x")</script>');
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
    expect(container.querySelector("strong")?.textContent).toBe("<img src=x onerror=alert(1)>");
    expect(container.textContent).toContain('<a href="javascript:alert(1)">link</a>');
  });

  it("shows `empty` when there is no text", () => {
    render(<FormattedText text="  " empty={<p>Nothing yet.</p>} />);
    expect(screen.getByText("Nothing yet.")).toBeTruthy();
  });
});

describe("FormattedTextEditor", () => {
  function Harness({ limit = 50 }: { limit?: number }) {
    const [value, setValue] = useState("");
    return <FormattedTextEditor label="Answer" value={value} onChange={setValue} limit={limit} />;
  }

  it("is a labelled textarea with the hint and the count linked to it", () => {
    render(<Harness />);
    const box = screen.getByLabelText("Answer");
    expect(box.tagName).toBe("TEXTAREA");
    expect(box.getAttribute("maxlength")).toBe("50");
    const described = (box.getAttribute("aria-describedby") ?? "")
      .split(" ")
      .map((id) => document.getElementById(id)?.textContent ?? "")
      .join(" ");
    expect(described).toContain("*bold*");
    expect(described).toContain("0 / 50 characters");
  });

  it("previews the text as the user types", () => {
    render(<Harness />);
    const preview = screen.getByRole("group", { name: "Preview of Answer" });
    expect(preview.textContent).toContain("Nothing to preview yet.");
    fireEvent.change(screen.getByLabelText("Answer"), { target: { value: "*Yes* <b>" } });
    expect(preview.querySelector("strong")?.textContent).toBe("Yes");
    expect(preview.querySelector("b")).toBeNull();
    expect(screen.getByText("9 / 50 characters")).toBeTruthy();
  });

  it("says when the text is too long, in words", () => {
    expect(lengthText("abcdef", 5)).toBe("6 / 5 characters · too long");
    expect(lengthText("₹ नमस्ते", 4000)).toBe("8 / 4,000 characters");
  });
});
