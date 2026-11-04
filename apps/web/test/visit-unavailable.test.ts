import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { VisitUnavailable } from "../src/components/leads/VisitUnavailable";

describe("VisitUnavailable (task 5.8)", () => {
  it("offers calls or WhatsApp only when the page shows a number", () => {
    const withPhone = renderToStaticMarkup(
      React.createElement(VisitUnavailable, { canCall: true }),
    );
    expect(withPhone).toContain("No project is open for site visits right now.");
    expect(withPhone).toContain("or call or WhatsApp us");
    const without = renderToStaticMarkup(React.createElement(VisitUnavailable, { canCall: false }));
    expect(without).not.toContain("WhatsApp");
    expect(without).toContain("Send us a question below.");
  });
});
