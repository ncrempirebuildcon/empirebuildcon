import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PageView } from "../src/components/blocks/PageView";

function legalPage(blocks: { type: string; data: Record<string, unknown> }[]) {
  return {
    slug: "terms",
    title: "Terms of use",
    kind: "legal",
    is_draft_text: false,
    legal_version: "1.2",
    seo: null,
    blocks: blocks.map((b, i) => ({ id: `b${i}`, sort_order: i, is_visible: true, ...b })),
  } as unknown as Parameters<typeof PageView>[0]["page"];
}

describe("PageView", () => {
  it("shows a legal page's version under its title", () => {
    const html = renderToStaticMarkup(
      React.createElement(PageView, {
        page: legalPage([{ type: "rich_text", data: { body: "Text" } }]),
        path: "/terms",
      }),
    );
    expect(html.indexOf("Terms of use")).toBeLessThan(html.indexOf("Version 1.2"));
  });

  it("shows the version under a leading hero, not above it", () => {
    const html = renderToStaticMarkup(
      React.createElement(PageView, {
        page: legalPage([
          { type: "hero", data: { heading: "Our terms" } },
          { type: "rich_text", data: { body: "Body text" } },
        ]),
        path: "/terms",
      }),
    );
    const hero = html.indexOf("Our terms");
    const version = html.indexOf("Version 1.2");
    expect(hero).toBeGreaterThan(-1);
    expect(version).toBeGreaterThan(hero);
    expect(version).toBeLessThan(html.indexOf("Body text"));
  });
});
