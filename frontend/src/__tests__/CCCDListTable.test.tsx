import { fireEvent, render, screen } from "@testing-library/react";

import CCCDListTable from "@/components/list/CCCDListTable";
import { rowFromResult, type ListRow } from "@/lib/cccdList";

const FULL = { id_number: 1, full_name: 1, dob: 1, gender: 1, residence: 1 };

function makeRow(confidences: Record<string, number> = FULL): ListRow {
  return rowFromResult(
    {
      id_number: "001202000123",
      full_name: "NGUYỄN VĂN A",
      dob: "01/01/2002",
      gender: "Nam",
      nationality: "Việt Nam",
      origin: "Hà Nội",
      residence: "Hà Nội",
      expiry_date: null,
    },
    confidences,
    "scan-1",
    "a.jpg",
  );
}

function renderTable(rows: ListRow[]) {
  const props = {
    rows,
    onUpdate: vi.fn(),
    onMarkReviewed: vi.fn(),
    onMerge: vi.fn(),
    onRemove: vi.fn(),
    onAdd: vi.fn(),
    onClear: vi.fn(),
    onExport: vi.fn(),
  };
  render(<CCCDListTable {...props} />);
  return props;
}

describe("CCCDListTable", () => {
  it("exports a fully valid list on the first click", () => {
    const props = renderTable([makeRow()]);
    fireEvent.click(screen.getByRole("button", { name: "Xuất Excel (1 người)" }));
    expect(props.onExport).toHaveBeenCalledTimes(1);
  });

  it("blocks export while a row has missing or inconsistent data", () => {
    const props = renderTable([{ ...makeRow(), gender: "Nữ" }]);
    expect(screen.getByText(/Không khớp số CCCD/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Xuất Excel (1 người)" })).toBeDisabled();
    expect(props.onExport).not.toHaveBeenCalled();
  });

  it("asks for a second click when low-confidence cells were not reviewed", () => {
    const props = renderTable([makeRow({ ...FULL, full_name: 0.5 })]);
    expect(screen.getByText("1 ô cần kiểm tra")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Xuất Excel (1 người)" }));
    expect(props.onExport).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Vẫn xuất Excel (1 người)" }));
    expect(props.onExport).toHaveBeenCalledTimes(1);
  });

  it("asks again when the number of unreviewed cells changes after the first click", () => {
    const one = makeRow({ ...FULL, full_name: 0.5 });
    const props = {
      onUpdate: vi.fn(), onMarkReviewed: vi.fn(), onMerge: vi.fn(), onRemove: vi.fn(),
      onAdd: vi.fn(), onClear: vi.fn(), onExport: vi.fn(),
    };
    const { rerender } = render(<CCCDListTable rows={[one]} {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Xuất Excel (1 người)" }));
    const two = { ...makeRow({ ...FULL, residence: 0.5 }), id_number: "079305000456", dob: "02/03/2005", gender: "Nữ", key: "k2" };
    rerender(<CCCDListTable rows={[one, two]} {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Xuất Excel (2 người)" }));
    expect(props.onExport).not.toHaveBeenCalled();
  });

  it("edits, deletes and adds rows through callbacks", () => {
    const row = makeRow();
    const props = renderTable([row]);
    fireEvent.change(screen.getByLabelText("Họ và tên dòng 1"), { target: { value: "TRẦN THỊ B" } });
    expect(props.onUpdate).toHaveBeenCalledWith(row.key, "full_name", "TRẦN THỊ B");
    fireEvent.click(screen.getByRole("button", { name: "Xóa dòng 1" }));
    expect(props.onRemove).toHaveBeenCalledWith(row.key);
    fireEvent.click(screen.getByRole("button", { name: "+ Thêm dòng" }));
    expect(props.onAdd).toHaveBeenCalled();
  });

  it("offers the gender encoded in the CCCD number", () => {
    const row = { ...makeRow(), gender: "Nữ" };
    const props = renderTable([row]);
    fireEvent.click(screen.getByRole("button", { name: "Theo số CCCD: Nam" }));
    expect(props.onUpdate).toHaveBeenCalledWith(row.key, "gender", "Nam");
  });

  it("warns about near-duplicate CCCD numbers and merges on request", () => {
    const front = { ...makeRow(), id_number: "001202000128", key: "f" };
    const back = { ...makeRow(), key: "b" };
    const props = renderTable([front, back]);
    expect(screen.getAllByText(/Gần giống số CCCD/)).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Gộp vào dòng 2" }));
    expect(props.onMerge).toHaveBeenCalledWith("f", "b");
  });

  it("needs two clicks to clear the whole list", () => {
    const props = renderTable([makeRow()]);
    fireEvent.click(screen.getByRole("button", { name: "Xóa tất cả" }));
    expect(props.onClear).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Bấm lần nữa để xóa hết" }));
    expect(props.onClear).toHaveBeenCalled();
  });
});
