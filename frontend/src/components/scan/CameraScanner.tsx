"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";

import {
  AUTO_CAPTURE_STABLE_FRAMES,
  CARD_ASPECT,
  FRAME_ISSUE_MESSAGES,
  FRAME_SAMPLE_WIDTH,
  GUIDE_WIDTH_RATIO,
  assessFrame,
  type FrameIssue,
} from "@/lib/frameQuality";

interface CameraScannerProps {
  onSubmit: (files: File[]) => void;
  isLoading: boolean;
  maxCaptures?: number;
}

interface Capture {
  file: File;
  url: string;
}

const ANALYZE_INTERVAL_MS = 250;
const CAPTURE_COOLDOWN_MS = 2000;

function cameraErrorMessage(err: unknown): string {
  const name = typeof err === "object" && err && "name" in err ? String(err.name) : "";
  if (name === "NotAllowedError") return "Chưa được cấp quyền dùng camera. Hãy cho phép trong cài đặt trình duyệt.";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "Không tìm thấy camera trên thiết bị.";
  if (name === "NotReadableError") return "Camera đang được ứng dụng khác sử dụng.";
  return "Không mở được camera.";
}

function canvasToJpeg(canvas: HTMLCanvasElement): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
}

export default function CameraScanner({ onSubmit, isLoading, maxCaptures = 20 }: CameraScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const sampleCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const previousLumaRef = useRef<Float32Array | null>(null);
  const stableFramesRef = useRef(0);
  const lastCaptureRef = useRef(0);
  const capturingRef = useRef(false);
  const captureSeqRef = useRef(0);
  // Sau mỗi lần tự chụp phải chờ khung hình "không đạt" (rút/đổi thẻ) mới tự chụp tiếp,
  // nếu không thẻ để yên sẽ bị chụp trùng mỗi CAPTURE_COOLDOWN_MS.
  const autoArmedRef = useRef(true);

  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issues, setIssues] = useState<FrameIssue[]>([]);
  const [autoCapture, setAutoCapture] = useState(true);
  const [captures, setCaptures] = useState<Capture[]>([]);
  const [flash, setFlash] = useState(false);

  const capturesRef = useRef(captures);

  useEffect(() => {
    // Camera chỉ chạy trong secure context (HTTPS hoặc localhost).
    if (!navigator.mediaDevices?.getUserMedia) {
      queueMicrotask(() =>
        setError("Trình duyệt không hỗ trợ camera hoặc trang không chạy qua HTTPS."),
      );
      return;
    }
    let stream: MediaStream | null = null;
    let cancelled = false;
    navigator.mediaDevices
      .getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      })
      .then(async (s) => {
        if (cancelled) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        stream = s;
        const video = videoRef.current;
        if (!video) return;
        video.srcObject = s;
        await video.play().catch(() => undefined);
        setReady(true);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(cameraErrorMessage(err));
      });
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  useEffect(
    () => () => {
      for (const c of capturesRef.current) URL.revokeObjectURL(c.url);
    },
    [],
  );

  const capture = useCallback(async () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth || capturingRef.current) return;
    if (capturesRef.current.length >= maxCaptures) return;
    capturingRef.current = true;
    try {
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d")?.drawImage(video, 0, 0);
      const blob = await canvasToJpeg(canvas);
      if (!blob) return;
      const file = new File([blob], `camera-${++captureSeqRef.current}.jpg`, { type: "image/jpeg" });
      const next = [...capturesRef.current, { file, url: URL.createObjectURL(file) }];
      capturesRef.current = next;
      setCaptures(next);
      lastCaptureRef.current = Date.now();
      stableFramesRef.current = 0;
      setFlash(true);
      setTimeout(() => setFlash(false), 150);
    } finally {
      capturingRef.current = false;
    }
  }, [maxCaptures]);

  useEffect(() => {
    if (!ready) return;
    const timer = setInterval(() => {
      const video = videoRef.current;
      if (!video || !video.videoWidth) return;
      const width = FRAME_SAMPLE_WIDTH;
      const height = Math.round((video.videoHeight / video.videoWidth) * width);
      const canvas = (sampleCanvasRef.current ??= document.createElement("canvas"));
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return;
      ctx.drawImage(video, 0, 0, width, height);
      const frame = assessFrame(
        ctx.getImageData(0, 0, width, height).data,
        width,
        height,
        previousLumaRef.current,
      );
      previousLumaRef.current = frame.luma;
      setIssues(frame.issues);

      stableFramesRef.current = frame.ok ? stableFramesRef.current + 1 : 0;
      if (!frame.ok) autoArmedRef.current = true;
      const cooledDown = Date.now() - lastCaptureRef.current > CAPTURE_COOLDOWN_MS;
      if (
        autoCapture &&
        autoArmedRef.current &&
        cooledDown &&
        stableFramesRef.current >= AUTO_CAPTURE_STABLE_FRAMES
      ) {
        autoArmedRef.current = false;
        void capture();
      }
    }, ANALYZE_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [ready, autoCapture, capture]);

  const removeCapture = (index: number) => {
    const target = capturesRef.current[index];
    if (target) URL.revokeObjectURL(target.url);
    const next = capturesRef.current.filter((_, i) => i !== index);
    capturesRef.current = next;
    setCaptures(next);
  };

  const submit = () => {
    if (captures.length === 0) return;
    onSubmit(captures.map((c) => c.file));
    for (const c of captures) URL.revokeObjectURL(c.url);
    capturesRef.current = [];
    setCaptures([]);
  };

  const frameOk = ready && issues.length === 0;
  const full = captures.length >= maxCaptures;

  if (error) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        <p className="font-semibold">{error}</p>
        <p className="mt-1">Bạn vẫn có thể dùng tab &quot;Tải file&quot; để chọn ảnh có sẵn.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="relative mx-auto w-full max-w-2xl overflow-hidden rounded-lg bg-black">
        <video ref={videoRef} className="block w-full" playsInline muted aria-label="Khung hình camera" />
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div
            className={`rounded-xl border-4 transition-colors ${
              frameOk ? "border-emerald-400" : "border-amber-400"
            }`}
            style={{ width: `${GUIDE_WIDTH_RATIO * 100}%`, aspectRatio: String(CARD_ASPECT) }}
          />
        </div>
        {flash && <div className="absolute inset-0 bg-white/70" />}
        <div className="absolute inset-x-0 bottom-0 bg-black/60 px-3 py-2 text-center text-sm text-white">
          {!ready
            ? "Đang mở camera..."
            : full
              ? `Đã đủ ${maxCaptures} ảnh`
              : frameOk
                ? autoCapture
                  ? "Giữ yên, đang tự chụp..."
                  : "Khung hình tốt, bấm Chụp"
                : FRAME_ISSUE_MESSAGES[issues[0] ?? "blurry"]}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-center gap-3">
        <button
          type="button"
          onClick={() => void capture()}
          disabled={!ready || full || isLoading}
          className="rounded-md bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:bg-gray-400"
        >
          Chụp
        </button>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={autoCapture}
            onChange={(e) => setAutoCapture(e.target.checked)}
          />
          Tự chụp khi khung hình đạt
        </label>
      </div>

      {captures.length > 0 && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
            {captures.map((c, i) => (
              <div key={c.url} className="relative overflow-hidden rounded-md border border-gray-200">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={c.url} alt={c.file.name} className="aspect-[1.586/1] w-full object-cover" />
                <button
                  type="button"
                  onClick={() => removeCapture(i)}
                  className="absolute right-1 top-1 rounded bg-black/60 px-1.5 text-xs text-white"
                  aria-label={`Xóa ${c.file.name}`}
                >
                  Xóa
                </button>
              </div>
            ))}
          </div>
          <div className="text-center">
            <button
              type="button"
              onClick={submit}
              disabled={isLoading}
              className="rounded-md bg-emerald-600 px-5 py-2 font-semibold text-white hover:bg-emerald-700 disabled:bg-gray-400"
            >
              {isLoading ? "Đang xử lý..." : `Xử lý ${captures.length} ảnh`}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
