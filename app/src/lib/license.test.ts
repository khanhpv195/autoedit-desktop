import { test, expect } from "vitest";
import raw from "../../../license-server/test/key-vectors.json";
import { licenseMessage, normalizeKey } from "./license";

const vectors = raw as [string, string][];

test("normalizeKey matches the shared vectors", () => {
  expect(vectors.length).toBeGreaterThanOrEqual(8);
  for (const [raw, want] of vectors) expect(normalizeKey(raw)).toBe(want);
});

test("every license code has its own message", () => {
  for (const c of ["LICENSE_REQUIRED", "LICENSE_MACHINE", "LICENSE_STORE", "LICENSE_CONFIG"]) {
    expect(licenseMessage(c)).not.toBe(licenseMessage("LICENSE_OFFLINE"));
  }
  expect(licenseMessage("LICENSE_REQUIRED")).toBe("Cần kích hoạt AutoEdit trước");
});
