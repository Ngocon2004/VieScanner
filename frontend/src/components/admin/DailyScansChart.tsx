"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";

import type { AdminOverview } from "@/lib/admin";

type Day = AdminOverview["daily"][number];

// Bảng màu categorical slot 1-2 (đã kiểm tra CVD trên nền trắng); chữ luôn dùng màu chữ, không dùng màu chuỗi.
const SERIES = [
  { key: "success", label: "Thành công", color: "#2a78d6" },
  { key: "failed", label: "Thất bại", color: "#eb6834" },
] as const;

const WIDTH = 720;
const HEIGHT = 220;
const PAD = { top: 12, right: 8, bottom: 28, left: 36 };
const GAP = 2;

/** Đỉnh trục Y "tròn" và chẵn, để mốc giữa (max/2) luôn là số nguyên. */
function niceMax(value: number): number {
  if (value <= 4) return 4;
  const step = 2 * 10 ** Math.floor(Math.log10(value / 2));
  return Math.ceil(value / step) * step;
}

function shortDate(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

export default function DailyScansChart({ daily }: { daily: Day[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Màn hình hẹp: biểu đồ cuộn ngang, mở sẵn ở cuối để thấy ngay những ngày gần nhất.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [asTable, daily]);
  const max = useMemo(() => niceMax(Math.max(0, ...daily.map((d) => d.success + d.failed))), [daily]);

  const plotW = WIDTH - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const slot = plotW / Math.max(1, daily.length);
  const barW = Math.max(2, Math.min(28, slot * 0.6));
  const y = (v: number) => PAD.top + plotH - (v / max) * plotH;
  const ticks = [0, max / 2, max];
  const labelEvery = Math.ceil(daily.length / 8);
  const hovered = hover === null ? null : daily[hover];

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-4 text-xs text-gray-600" aria-label="Chú thích">
          {SERIES.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setAsTable((v) => !v)}
          className="text-xs font-medium text-blue-700 underline"
        >
          {asTable ? "Xem biểu đồ" : "Xem dạng bảng"}
        </button>
      </div>

      {asTable ? (
        <div className="max-h-64 overflow-auto">
          <table className="w-full text-left text-sm tabular-nums">
            <thead className="sticky top-0 bg-white text-xs text-gray-500">
              <tr><th className="py-1">Ngày</th><th>Thành công</th><th>Thất bại</th></tr>
            </thead>
            <tbody>
              {daily.map((d) => (
                <tr key={d.date} className="border-t border-gray-100">
                  <td className="py-1">{shortDate(d.date)}</td><td>{d.success}</td><td>{d.failed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={scrollRef} className="overflow-x-auto">
          <div className="relative min-w-[560px]">
            <svg
              viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
              className="h-auto w-full"
              role="img"
              aria-label="Số lượt quét theo ngày, chia thành công và thất bại"
              onMouseLeave={() => setHover(null)}
            >
              {ticks.map((t) => (
                <g key={t}>
                  <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? "#c3c2b7" : "#e1e0d9"} strokeWidth={1} />
                  <text x={PAD.left - 6} y={y(t) + 4} textAnchor="end" fontSize={11} fill="#898781">
                    {t}
                  </text>
                </g>
              ))}
              {daily.map((d, i) => {
                const cx = PAD.left + slot * i + slot / 2;
                const x = cx - barW / 2;
                const successTop = y(d.success);
                const failedTop = y(d.success + d.failed);
                const failedH = Math.max(0, successTop - failedTop - (d.success > 0 ? GAP : 0));
                return (
                  <g key={d.date}>
                    {hover === i && <rect x={cx - slot / 2} y={PAD.top} width={slot} height={plotH} fill="#f0efec" />}
                    {d.success > 0 && (
                      <path d={roundedTop(x, successTop, barW, y(0) - successTop, d.failed === 0)} fill={SERIES[0].color} />
                    )}
                    {d.failed > 0 && failedH > 0 && (
                      <path d={roundedTop(x, failedTop, barW, failedH, true)} fill={SERIES[1].color} />
                    )}
                    {i % labelEvery === 0 && (
                      <text x={cx} y={HEIGHT - 8} textAnchor="middle" fontSize={11} fill="#898781">
                        {shortDate(d.date)}
                      </text>
                    )}
                    <rect
                      x={cx - slot / 2}
                      y={PAD.top}
                      width={slot}
                      height={plotH}
                      fill="transparent"
                      onMouseEnter={() => setHover(i)}
                    />
                  </g>
                );
              })}
            </svg>
            {hovered && hover !== null && (
              <div
                className="pointer-events-none absolute top-2 z-10 whitespace-nowrap rounded-md border border-gray-200 bg-white px-3 py-2 text-xs shadow-md tabular-nums"
                style={{
                  left: `${((PAD.left + slot * hover + slot / 2) / WIDTH) * 100}%`,
                  transform: hover > daily.length / 2 ? "translateX(-105%)" : "translateX(5%)",
                }}
              >
                <div className="mb-1 font-semibold text-gray-900">{shortDate(hovered.date)}</div>
                {SERIES.map((s) => (
                  <div key={s.key} className="flex items-center gap-2 text-gray-700">
                    <span className="h-2 w-2 rounded-sm" style={{ background: s.color }} />
                    {s.label}: <span className="font-semibold text-gray-900">{hovered[s.key]}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Cột có đầu trên bo 4px (đầu dữ liệu), đáy vuông nằm trên trục. */
function roundedTop(x: number, top: number, w: number, h: number, round: boolean): string {
  const r = round ? Math.min(4, w / 2, h) : 0;
  return `M${x},${top + h} V${top + r} Q${x},${top} ${x + r},${top} H${x + w - r} Q${x + w},${top} ${x + w},${top + r} V${top + h} Z`;
}
