import {
  applyEdit,
  decodeIdNumber,
  mergeRowInto,
  nearDuplicateIds,
  pendingReviewCount,
  mergeIntoList,
  needsReview,
  normalizeStoredRow,
  rowFromResult,
  toExportRows,
  validateList,
  validateRow,
  type ListRow,
} from "@/lib/cccdList";
import type { CCCDData } from "@/lib/schemas";

const FRONT: CCCDData = {
  id_number: "001202000123",
  full_name: "NGUYỄN VĂN A",
  dob: "01/01/2002",
  gender: "Nam",
  nationality: "Việt Nam",
  origin: "Hà Nội",
  residence: "Phường Ba Đình, Hà Nội",
  expiry_date: null,
};

const FULL_CONFIDENCE = { id_number: 1, full_name: 1, dob: 1, gender: 1, residence: 1 };

describe("rowFromResult", () => {
  it("drops OCR placeholders instead of keeping fake values", () => {
    const back: CCCDData = {
      ...FRONT,
      full_name: "(không nhận dạng được)",
      residence: "(không nhận dạng được)",
    };
    const row = rowFromResult(back, { id_number: 1, dob: 1, gender: 1, full_name: 0, residence: 0 }, "s2", "back.jpg");
    expect(row.full_name).toBe("");
    expect(row.residence).toBe("");
    expect(row.id_number).toBe("001202000123");
    expect(row.scanIds).toEqual(["s2"]);
  });

  it("keeps zero-confidence defaults out of the list; gender then comes from the CCCD number", () => {
    const row = rowFromResult({ ...FRONT, dob: "01/01/2000" }, { ...FULL_CONFIDENCE, dob: 0, gender: 0 }, null, "a.jpg");
    expect(row.dob).toBe("");
    expect(row.gender).toBe("Nam");
    const noId = rowFromResult({ ...FRONT, dob: "01/01/2000" }, { ...FULL_CONFIDENCE, id_number: 0, gender: 0 }, null, "a.jpg");
    expect(noId.gender).toBe("");
  });
});

describe("validateRow", () => {
  const valid = rowFromResult(FRONT, FULL_CONFIDENCE, null, "a.jpg");

  it("accepts a complete row that matches its CCCD number", () => {
    expect(validateRow(valid)).toEqual({});
  });

  it.each<[Partial<ListRow>, keyof ListRow, RegExp]>([
    [{ full_name: "" }, "full_name", /Chưa có/],
    [{ id_number: "00120200012" }, "id_number", /12 chữ số/],
    [{ id_number: "999202000123" }, "id_number", /không hợp lệ/],
    [{ dob: "31/02/2002" }, "dob", /không hợp lệ/],
    [{ dob: "01/01/2003" }, "dob", /không khớp số CCCD \(2002\)/],
    [{ gender: "Nữ" }, "gender", /Không khớp số CCCD/],
    [{ full_name: "NGUYỄN VĂN A1" }, "full_name", /chữ số/],
    [{ dob: "01/01/2099" }, "dob", /tương lai/],
  ])("flags %o", (patch, field, message) => {
    expect(validateRow({ ...valid, ...patch })[field as keyof ReturnType<typeof validateRow>]).toMatch(message);
  });

  it("decodes century and gender from the CCCD number", () => {
    expect(decodeIdNumber("079305000456")).toEqual({ gender: "Nữ", birthYear: 2005 });
    expect(decodeIdNumber("001090000001")).toEqual({ gender: "Nam", birthYear: 1990 });
  });

  it("flags duplicated CCCD numbers across rows", () => {
    const other = { ...valid, key: "other" };
    expect(validateList([valid, other]).get("other")?.id_number).toMatch(/Trùng/);
  });
});

describe("mergeIntoList", () => {
  it("merges the back side into the front row of the same card", () => {
    const front = rowFromResult(FRONT, { ...FULL_CONFIDENCE, dob: 0.7 }, "s1", "front.jpg");
    const back = rowFromResult(
      { ...FRONT, full_name: "(không nhận dạng được)", residence: "(không nhận dạng được)" },
      { id_number: 1, dob: 1, gender: 1 },
      "s2",
      "back.jpg",
    );
    const rows = mergeIntoList([front], back);
    expect(rows).toHaveLength(1);
    expect(rows[0]!.full_name).toBe("NGUYỄN VĂN A");
    expect(rows[0]!.confidences.dob).toBe(1);
    expect(rows[0]!.scanIds).toEqual(["s1", "s2"]);
    expect(toExportRows(rows)[0]!.scan_ids).toEqual(["s1", "s2"]);
  });

  it("never overwrites a field the user already corrected", () => {
    const front = { ...rowFromResult(FRONT, FULL_CONFIDENCE, null, "a.jpg"), full_name: "SỬA TAY", reviewed: { full_name: true } };
    const again = rowFromResult(FRONT, FULL_CONFIDENCE, null, "b.jpg");
    expect(mergeIntoList([front], again)[0]!.full_name).toBe("SỬA TAY");
  });

  it("appends rows without a valid CCCD number instead of merging them", () => {
    const unknown = rowFromResult(FRONT, { ...FULL_CONFIDENCE, id_number: 0 }, null, "a.jpg");
    expect(mergeIntoList([unknown], { ...unknown, key: "k2" })).toHaveLength(2);
  });
});

describe("normalizeStoredRow", () => {
  it("drops broken entries and fills missing fields from old or corrupted storage", () => {
    expect(normalizeStoredRow(null)).toBeNull();
    expect(normalizeStoredRow({ full_name: "A" })).toBeNull();
    const row = normalizeStoredRow({ key: "k1", full_name: "A", scanIds: ["s1", 3], reviewed: "x" });
    expect(row).toMatchObject({ key: "k1", full_name: "A", id_number: "", scanIds: ["s1"], reviewed: {} });
  });
});

describe("needsReview", () => {
  it("asks to review low-confidence cells until the user confirms them", () => {
    const row = rowFromResult(FRONT, { ...FULL_CONFIDENCE, full_name: 0.6 }, null, "a.jpg");
    expect(needsReview(row, "full_name")).toBe(true);
    expect(needsReview(row, "id_number")).toBe(false);
    expect(needsReview({ ...row, reviewed: { full_name: true } }, "full_name")).toBe(false);
  });
});

describe("gender from the CCCD number", () => {
  it("derives a missing gender and trusts a gender that agrees with the number", () => {
    const missing = rowFromResult(FRONT, { ...FULL_CONFIDENCE, gender: 0, id_number: 0.9 }, null, "a.jpg");
    expect(missing.gender).toBe("Nam");
    expect(missing.confidences.gender).toBe(0.9);
    const agreeing = rowFromResult(FRONT, { ...FULL_CONFIDENCE, gender: 0.6, id_number: 0.9 }, null, "a.jpg");
    expect(agreeing.confidences.gender).toBe(0.9);
    expect(needsReview(agreeing, "gender")).toBe(false);
  });

  it("follows an edited CCCD number unless the user picked the gender", () => {
    const row = rowFromResult(FRONT, FULL_CONFIDENCE, null, "a.jpg");
    expect(applyEdit(row, "id_number", "079305000456").gender).toBe("Nữ");
    const picked = applyEdit(row, "gender", "Nam");
    expect(applyEdit(picked, "id_number", "079305000456").gender).toBe("Nam");
  });
});

describe("near-duplicate CCCD numbers", () => {
  it("flags rows whose numbers differ by one or two digits and lets them merge", () => {
    const front = { ...rowFromResult(FRONT, FULL_CONFIDENCE, "s1", "front.jpg"), id_number: "001202000128", key: "f" };
    const back = { ...rowFromResult(FRONT, FULL_CONFIDENCE, "s2", "back.jpg"), full_name: "", residence: "", key: "b" };
    const near = nearDuplicateIds([front, back]);
    expect(near.get("f")).toBe(2);
    expect(near.get("b")).toBe(1);
    expect(pendingReviewCount([front, back])).toBe(2);
    const merged = mergeRowInto(back, front);
    expect(merged.full_name).toBe("NGUYỄN VĂN A");
    expect(merged.id_number).toBe("001202000123");
    expect(merged.scanIds).toEqual(["s2", "s1"]);
  });

  it("ignores numbers that differ by three or more digits", () => {
    const a = rowFromResult(FRONT, FULL_CONFIDENCE, null, "a.jpg");
    const b = { ...a, key: "other", id_number: "001202999123" };
    expect(nearDuplicateIds([a, b]).size).toBe(0);
  });
});

describe("hints for fields that need the other side of the card", () => {
  it("tells which side to upload and drops the hint once the field is filled by a merge", () => {
    const front2024 = rowFromResult(
      { ...FRONT, residence: "(không nhận dạng được)" },
      { ...FULL_CONFIDENCE, residence: 0 },
      "s1",
      "front.jpg",
      ["residence_on_back"],
    );
    expect(validateRow(front2024).residence).toMatch(/mặt sau/);
    const back = rowFromResult(FRONT, { id_number: 1, dob: 1, gender: 1, residence: 0.8 }, "s2", "back.jpg", ["back_side"]);
    const [merged] = mergeIntoList([front2024], back);
    expect(merged!.residence).toBe(FRONT.residence);
    expect(merged!.hints).toEqual({});
  });
});
