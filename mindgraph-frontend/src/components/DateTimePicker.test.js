import { useRef } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DateTimePicker from "./DateTimePicker";

function PickerHarness({ currentDate = "2026-04-13" , onSave, onCancel }) {
  const anchorRef = useRef(null);

  return (
    <div>
      <button type="button" ref={anchorRef}>
        Anchor
      </button>
      <DateTimePicker
        currentDate={currentDate}
        anchorRef={anchorRef}
        onSave={onSave}
        onCancel={onCancel}
      />
    </div>
  );
}

describe("DateTimePicker", () => {
  test("selects a day and saves an optional time", () => {
    const onSave = jest.fn();
    const onCancel = jest.fn();

    render(
      <PickerHarness
        currentDate="2026-04-13"
        onSave={onSave}
        onCancel={onCancel}
      />
    );

    userEvent.click(screen.getByRole("button", { name: /April 17, 2026/i }));

    const hourInput = screen.getByLabelText(/deadline hour/i);
    const minuteInput = screen.getByLabelText(/deadline minute/i);

    userEvent.clear(hourInput);
    userEvent.type(hourInput, "08");
    userEvent.clear(minuteInput);
    userEvent.type(minuteInput, "45");

    userEvent.click(screen.getByRole("button", { name: /save deadline date/i }));

    expect(onSave).toHaveBeenCalledWith("2026-04-17T08:45");
    expect(onCancel).not.toHaveBeenCalled();
  });
});
