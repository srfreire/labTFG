import { describe, expect, it } from "vitest";

import {
  formatKgPropertyValue,
  shouldShowKgProperty,
} from "./kgDisplay";

describe("kgDisplay", () => {
  it("hides embedding and internal vector fields", () => {
    expect(shouldShowKgProperty("embedding", [0.1, 0.2])).toBe(false);
    expect(shouldShowKgProperty("text_embedding", [0.1, 0.2])).toBe(false);
    expect(shouldShowKgProperty("dense_vector", [0.1, 0.2])).toBe(false);
    expect(shouldShowKgProperty("_synthetic_id", "x")).toBe(false);
  });

  it("hides long numeric arrays even when the key is unfamiliar", () => {
    expect(
      shouldShowKgProperty(
        "payload",
        Array.from({ length: 32 }, (_, i) => i / 10),
      ),
    ).toBe(false);
  });

  it("keeps ordinary semantic properties visible", () => {
    expect(shouldShowKgProperty("symbol", "mu_t")).toBe(true);
    expect(shouldShowKgProperty("latex", "\\mu_t = x")).toBe(true);
    expect(shouldShowKgProperty("description", "posterior mean")).toBe(true);
  });

  it("formats null values compactly", () => {
    expect(formatKgPropertyValue(null)).toBe("-");
  });
});
