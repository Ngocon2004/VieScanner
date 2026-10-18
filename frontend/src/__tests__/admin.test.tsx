import { fireEvent, render, screen } from "@testing-library/react";

import { ErrorBars, FieldQualityTable, StatTiles } from "@/components/admin/AdminPanels";
import DailyScansChart from "@/components/admin/DailyScansChart";
import UsersTable from "@/components/admin/UsersTable";
import { errorLabel, type AdminOverview, type AdminUser } from "@/lib/admin";

const OVERVIEW: AdminOverview = {
  days: 3,
  totals: {
    scans: 10, succeeded: 8, failed: 2, median_duration_ms: 1200, p90_duration_ms: 2800,
    users: 4, new_users: 1, exported_scans: 5, corrections: 3, active_jobs: 0,
  },
  daily: [
    { date: "2026-10-13", success: 2, failed: 0 },
    { date: "2026-10-14", success: 3, failed: 1 },
    { date: "2026-10-15", success: 3, failed: 1 },
  ],
  errors: [{ code: "image_quality_low", count: 2 }],
  fields: [{ field: "full_name", read: 6, read_rate: 0.75, low_confidence: 2, corrected: 1, corrected_rate: 0.2 }],
  jobs: { completed: 2 },
};

function user(patch: Partial<AdminUser>): AdminUser {
  return {
    id: "u1", email: "a@x.vn", full_name: "A", role: "user", is_active: true,
    created_at: "2026-10-01T00:00:00Z", scans: 3, exported_scans: 1, last_scan_at: null, ...patch,
  };
}

describe("admin dashboard", () => {
  it("shows headline numbers as stat tiles", () => {
    render(<StatTiles overview={OVERVIEW} />);
    expect(screen.getByText("80%")).toBeInTheDocument();
    expect(screen.getByText("1,2 s")).toBeInTheDocument();
  });

  it("charts daily scans with a legend and a table view", () => {
    render(<DailyScansChart daily={OVERVIEW.daily} />);
    expect(screen.getByRole("img", { name: /Số lượt quét theo ngày/ })).toBeInTheDocument();
    expect(screen.getByText("Thành công")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Xem dạng bảng" }));
    expect(screen.getByRole("cell", { name: "14/10" })).toBeInTheDocument();
  });

  it("labels failure reasons and field quality in Vietnamese", () => {
    render(<><ErrorBars errors={OVERVIEW.errors} /><FieldQualityTable overview={OVERVIEW} /></>);
    expect(screen.getByText("Ảnh không đạt chất lượng")).toBeInTheDocument();
    expect(screen.getByText("Họ và tên")).toBeInTheDocument();
    expect(screen.getByText("(20%)")).toBeInTheDocument();
  });

  it("lets an admin change other users but not their own account", () => {
    const onUpdate = vi.fn();
    render(
      <UsersTable
        users={[user({ id: "me", email: "me@x.vn", role: "admin" }), user({})]}
        currentUserId="me"
        query=""
        onQueryChange={vi.fn()}
        onUpdate={onUpdate}
        busyId={null}
      />,
    );
    expect(screen.getByLabelText("Vai trò của me@x.vn")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Khóa a@x.vn" }));
    expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ id: "u1" }), { is_active: false });
    fireEvent.change(screen.getByLabelText("Vai trò của a@x.vn"), { target: { value: "admin" } });
    expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ id: "u1" }), { role: "admin" });
  });

  it("names OCR stage failures in Vietnamese and falls back to the raw code", () => {
    expect(errorLabel("ocr_aligner_failed")).toBe("Không tìm thấy đủ 4 góc thẻ");
    expect(errorLabel("ocr_recognizer_failed")).toBe("Lỗi bước nhận dạng chữ");
    expect(errorLabel(null)).toBe("Không rõ");
    expect(errorLabel("something_new")).toBe("something_new");
  });

  it("keeps the middle y-axis tick on a whole number", () => {
    render(<DailyScansChart daily={[{ date: "2026-10-15", success: 4, failed: 1 }]} />);
    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });
});
