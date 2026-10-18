import { assessFrame, countCardSides, guideRect, toLuma } from "@/lib/frameQuality";

const W = 320;
const H = 180;

function frame(pixel: (x: number, y: number) => number): Uint8ClampedArray {
  const data = new Uint8ClampedArray(W * H * 4);
  for (let y = 0; y < H; y += 1) {
    for (let x = 0; x < W; x += 1) {
      const v = pixel(x, y);
      const i = (y * W + x) * 4;
      data[i] = v;
      data[i + 1] = v;
      data[i + 2] = v;
      data[i + 3] = 255;
    }
  }
  return data;
}

const textured = (x: number, y: number) => ((x + y) % 2 === 0 ? 90 : 170);

// Thẻ sáng có "chữ" (sọc) nằm đúng khung hướng dẫn, nền tối có hoa văn.
function cardInGuide(dx = 0): (x: number, y: number) => number {
  const g = guideRect(W, H);
  return (x, y) => {
    const inside = x >= g.x + dx && x < g.x + g.width + dx && y >= g.y && y < g.y + g.height;
    if (!inside) return (x * 7 + y * 13) % 5 === 0 ? 60 : 40;
    return y % 6 < 2 && (x - dx) % 4 < 3 ? 70 : 215;
  };
}

describe("assessFrame", () => {
  it("flags dark frames", () => {
    expect(assessFrame(frame(() => 20), W, H, null).issues).toContain("too_dark");
  });

  it("flags flat (blurry) frames", () => {
    expect(assessFrame(frame(() => 128), W, H, null).issues).toContain("blurry");
  });

  it("flags glare", () => {
    expect(assessFrame(frame((x) => (x < W / 2 ? 255 : 120)), W, H, null).issues).toContain("glare");
  });

  it("needs a previous frame to judge motion", () => {
    const first = assessFrame(frame(cardInGuide()), W, H, null);
    expect(first.issues).toEqual(["moving"]);

    const steady = assessFrame(frame(cardInGuide()), W, H, first.luma);
    expect(steady.ok).toBe(true);

    const shifted = assessFrame(frame(cardInGuide(2)), W, H, steady.luma);
    expect(shifted.issues).toContain("moving");
  });

  it("does not auto-capture sharp scenes without a card in the guide", () => {
    const first = assessFrame(frame(textured), W, H, null);
    const steady = assessFrame(frame(textured), W, H, first.luma);
    expect(steady.issues).toEqual(["no_card"]);
  });
});

describe("countCardSides", () => {
  const sides = (pixel: (x: number, y: number) => number) => {
    const data = frame(pixel);
    return countCardSides(toLuma(data), W, H);
  };

  it("finds all four card edges, also when the card is a bit off the guide", () => {
    expect(sides(cardInGuide())).toBe(4);
    expect(sides(cardInGuide(12))).toBeGreaterThanOrEqual(3);
  });

  it("ignores flat and textured backgrounds", () => {
    expect(sides(() => 128)).toBe(0);
    expect(sides(textured)).toBe(0);
    let seed = 7;
    const noise = () => {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return 40 + (seed % 120);
    };
    expect(sides(noise)).toBeLessThan(3);
  });
});
