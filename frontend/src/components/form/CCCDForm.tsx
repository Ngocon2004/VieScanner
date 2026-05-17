"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";

import { CCCD_FIELDS } from "@/constants/fields";
import type { APIError } from "@/lib/api";
import {
  cccdDataSchema,
  type CCCDData,
  type FieldConfidences,
} from "@/lib/schemas";

interface CCCDFormProps {
  initialData: CCCDData;
  confidences?: FieldConfidences;
  onExport: (data: CCCDData) => void | Promise<void>;
  isExporting?: boolean;
  exportError?: APIError | null;
}

type FieldErrors = Partial<Record<keyof CCCDData, string>>;

function getFieldErrors(data: CCCDData): FieldErrors {
  const parsed = cccdDataSchema.safeParse(data);
  if (parsed.success) return {};

  const errors: FieldErrors = {};
  for (const issue of parsed.error.issues) {
    const field = issue.path[0];
    if (typeof field === "string" && field in data) {
      const fieldName = field as keyof CCCDData;
      errors[fieldName] ??= issue.message;
    }
  }
  return errors;
}

function getConfidenceMeta(confidence: number | undefined) {
  const base =
    "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold sm:text-xs";

  if (typeof confidence !== "number") {
    return {
      label: "--",
      className: `${base} border-gray-200 bg-gray-50 text-gray-500`,
      dotClassName: "bg-gray-400",
    };
  }

  const pct = `${Math.round(confidence * 100)}%`;
  if (confidence >= 0.85) {
    return {
      label: pct,
      className: `${base} border-emerald-200 bg-emerald-50 text-emerald-700`,
      dotClassName: "bg-emerald-500",
    };
  }

  if (confidence >= 0.6) {
    return {
      label: pct,
      className: `${base} border-amber-200 bg-amber-50 text-amber-700`,
      dotClassName: "bg-amber-500",
    };
  }

  return {
    label: pct,
    className: `${base} border-red-200 bg-red-50 text-red-700`,
    dotClassName: "bg-red-500",
  };
}

export default function CCCDForm({
  initialData,
  confidences = {},
  onExport,
  isExporting = false,
  exportError = null,
}: CCCDFormProps) {
  const [formData, setFormData] = useState<CCCDData>(initialData);
  const inputRefs = useRef<
    Partial<Record<keyof CCCDData, HTMLInputElement | null>>
  >({});

  const fieldErrors = useMemo(() => getFieldErrors(formData), [formData]);
  const hasValidationErrors = Object.keys(fieldErrors).length > 0;

  useEffect(() => {
    const lowest = CCCD_FIELDS.map((field) => ({
      name: field.name,
      confidence: confidences[field.name],
    }))
      .filter(
        (item): item is { name: keyof CCCDData; confidence: number } =>
          typeof item.confidence === "number",
      )
      .sort((a, b) => a.confidence - b.confidence)[0];

    if (lowest && lowest.confidence < 0.7) {
      inputRefs.current[lowest.name]?.focus();
    }
  }, [confidences]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name as keyof CCCDData]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (hasValidationErrors) return;
    void onExport(formData);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full space-y-4 rounded-lg bg-white p-4 shadow-md sm:p-6"
    >
      <h3 className="mb-4 text-lg font-bold text-gray-800 sm:text-xl">
        Kết quả nhận diện
      </h3>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {CCCD_FIELDS.map((field) => {
          const value = formData[field.name];
          const confidence = confidences[field.name];
          const confidenceMeta = getConfidenceMeta(confidence);
          const fieldError = fieldErrors[field.name];
          const inputClassName = fieldError
            ? "border-red-500 bg-red-50 focus:ring-red-500"
            : confidence !== undefined && confidence < 0.6
              ? "border-red-300 bg-red-50/60 focus:ring-red-500"
              : "border-gray-300 focus:ring-blue-500";

          return (
            <div key={field.name} className="flex flex-col">
              <div className="mb-1 flex min-h-6 flex-wrap items-center justify-between gap-2">
                <label
                  htmlFor={field.name}
                  className="min-w-0 pr-2 text-sm font-semibold text-gray-600"
                >
                  {field.label}
                </label>
                <span
                  className={confidenceMeta.className}
                  title="Độ tin cậy OCR"
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${confidenceMeta.dotClassName}`}
                    aria-hidden="true"
                  />
                  {confidenceMeta.label}
                </span>
              </div>
              <input
                id={field.name}
                ref={(node) => {
                  inputRefs.current[field.name] = node;
                }}
                type="text"
                name={field.name}
                value={value ?? ""}
                onChange={handleChange}
                placeholder={field.placeholder}
                aria-invalid={Boolean(fieldError)}
                aria-describedby={
                  fieldError || field.hint ? `${field.name}-help` : undefined
                }
                className={`w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 sm:text-base ${inputClassName}`}
              />
              {(fieldError || field.hint) && (
                <span
                  id={`${field.name}-help`}
                  className={`mt-1 text-xs ${
                    fieldError ? "text-red-600" : "text-gray-400"
                  }`}
                >
                  {fieldError ?? field.hint}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {exportError && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <div className="font-semibold">{exportError.message}</div>
          {exportError.requestId && (
            <div className="mt-1 text-xs text-red-500">
              request_id: {exportError.requestId}
            </div>
          )}
        </div>
      )}

      <div className="flex justify-end pt-2 sm:pt-4">
        <button
          type="submit"
          disabled={isExporting || hasValidationErrors}
          className="w-full rounded-md bg-green-600 px-6 py-2 font-bold text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:bg-gray-400 sm:w-auto"
        >
          {isExporting
            ? "Đang xuất..."
            : hasValidationErrors
              ? "Kiểm tra lại thông tin"
              : "Xuất file Excel"}
        </button>
      </div>
    </form>
  );
}
