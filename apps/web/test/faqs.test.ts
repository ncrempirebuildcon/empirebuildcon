// FAQ reorder sends the whole group (review L10): `PUT /admin/faqs/order` refuses a list that
// leaves any FAQ of the group out (422 FULL_LIST), so the CMS reads the group again and sends all.
import { describe, expect, it } from "vitest";
import { fullGroupOrder } from "@/lib/content/faqs";

describe("fullGroupOrder", () => {
  it("sends the order the user chose when nothing changed elsewhere", () => {
    expect(fullGroupOrder(["c", "a", "b"], ["a", "b", "c"])).toEqual(["c", "a", "b"]);
  });

  it("adds FAQs someone else added since the list loaded, at the end", () => {
    expect(fullGroupOrder(["b", "a"], ["a", "b", "new"])).toEqual(["b", "a", "new"]);
  });

  it("leaves out FAQs someone else deleted", () => {
    expect(fullGroupOrder(["b", "gone", "a"], ["a", "b"])).toEqual(["b", "a"]);
  });

  it("names every FAQ of a group longer than one page of the list", () => {
    const group = Array.from({ length: 230 }, (_, index) => `faq-${index}`);
    const moved = [group[1], group[0], ...group.slice(2)] as string[];
    const sent = fullGroupOrder(moved, group);
    expect(sent).toHaveLength(230);
    expect(new Set(sent)).toEqual(new Set(group));
    expect(sent.slice(0, 2)).toEqual(["faq-1", "faq-0"]);
  });
});
