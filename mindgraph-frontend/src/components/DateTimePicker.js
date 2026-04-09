import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import {
  buildDeadlineDueDate,
  parseDeadlineDate,
} from "../utils/dateHelpers";
import "../styles/datepicker.css";

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const VIEWPORT_GUTTER = 12;
const PICKER_GAP = 10;
const FALLBACK_PICKER_WIDTH = 320;
const FALLBACK_PICKER_HEIGHT = 360;

const stripTime = (value) => {
  const date = new Date(value);
  date.setHours(0, 0, 0, 0);
  return date;
};

const createDate = (year, month, day) => {
  const date = new Date(year, month, day);
  date.setHours(0, 0, 0, 0);
  return date;
};

const isSameDate = (left, right) =>
  Boolean(left) &&
  Boolean(right) &&
  left.getFullYear() === right.getFullYear() &&
  left.getMonth() === right.getMonth() &&
  left.getDate() === right.getDate();

const monthStart = (value) => createDate(value.getFullYear(), value.getMonth(), 1);

const monthLabel = (value) =>
  value.toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });

const buttonLabel = (value) =>
  value.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });

const buildCalendarDays = (visibleMonth) => {
  const firstDay = monthStart(visibleMonth);
  const mondayOffset = (firstDay.getDay() + 6) % 7;
  const firstVisibleDay = createDate(
    firstDay.getFullYear(),
    firstDay.getMonth(),
    firstDay.getDate() - mondayOffset
  );

  return Array.from({ length: 42 }, (_, index) =>
    createDate(
      firstVisibleDay.getFullYear(),
      firstVisibleDay.getMonth(),
      firstVisibleDay.getDate() + index
    )
  );
};

const sanitizeTimePart = (value) => String(value || "").replace(/\D/g, "").slice(0, 2);

const normalizeTimePart = (value) =>
  value === "" ? "" : String(value).padStart(2, "0").slice(-2);

const getInitialState = (currentDate) => {
  const parsed = parseDeadlineDate(currentDate);
  const selectedDate = parsed?.dateOnly ? stripTime(parsed.dateOnly) : stripTime(new Date());
  const [initialHour = "", initialMinute = ""] = parsed?.hasMeaningfulTime
    ? (parsed.timePart || "").split(":")
    : ["", ""];

  return {
    selectedDate,
    visibleMonth: monthStart(selectedDate),
    hour: initialHour,
    minute: initialMinute,
  };
};

export default function DateTimePicker({
  currentDate,
  onSave,
  onCancel,
  anchorRef,
}) {
  const initialState = getInitialState(currentDate);
  const [selectedDate, setSelectedDate] = useState(initialState.selectedDate);
  const [visibleMonth, setVisibleMonth] = useState(initialState.visibleMonth);
  const [hour, setHour] = useState(initialState.hour);
  const [minute, setMinute] = useState(initialState.minute);
  const [position, setPosition] = useState({
    top: 0,
    left: VIEWPORT_GUTTER,
    placement: "bottom",
    ready: false,
  });

  const pickerRef = useRef(null);

  useEffect(() => {
    const nextState = getInitialState(currentDate);
    setSelectedDate(nextState.selectedDate);
    setVisibleMonth(nextState.visibleMonth);
    setHour(nextState.hour);
    setMinute(nextState.minute);
  }, [currentDate]);

  useEffect(() => {
    const handlePointerDown = (event) => {
      const picker = pickerRef.current;
      const anchor = anchorRef?.current;
      const target = event.target;

      if (picker?.contains(target) || anchor?.contains(target)) {
        return;
      }

      onCancel();
    };

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        onCancel();
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [anchorRef, onCancel]);

  useLayoutEffect(() => {
    const updatePosition = () => {
      const picker = pickerRef.current;
      const anchor = anchorRef?.current;

      if (!picker || !anchor) {
        return;
      }

      const anchorRect = anchor.getBoundingClientRect();
      const pickerRect = picker.getBoundingClientRect();
      const width = pickerRect.width || FALLBACK_PICKER_WIDTH;
      const height = pickerRect.height || FALLBACK_PICKER_HEIGHT;

      let left = anchorRect.left;
      left = Math.min(left, window.innerWidth - width - VIEWPORT_GUTTER);
      left = Math.max(left, VIEWPORT_GUTTER);

      const belowTop = anchorRect.bottom + PICKER_GAP;
      const aboveTop = anchorRect.top - height - PICKER_GAP;
      const canOpenBelow =
        belowTop + height <= window.innerHeight - VIEWPORT_GUTTER;
      const canOpenAbove = aboveTop >= VIEWPORT_GUTTER;

      let top = canOpenBelow || !canOpenAbove ? belowTop : aboveTop;
      const placement = canOpenBelow || !canOpenAbove ? "bottom" : "top";

      top = Math.min(top, window.innerHeight - height - VIEWPORT_GUTTER);
      top = Math.max(top, VIEWPORT_GUTTER);

      setPosition({
        top,
        left,
        placement,
        ready: true,
      });
    };

    const requestFrame =
      window.requestAnimationFrame || ((callback) => window.setTimeout(callback, 0));
    const cancelFrame =
      window.cancelAnimationFrame || ((frame) => window.clearTimeout(frame));

    updatePosition();
    const frame = requestFrame(updatePosition);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    return () => {
      cancelFrame(frame);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [anchorRef, visibleMonth]);

  const days = buildCalendarDays(visibleMonth);
  const today = stripTime(new Date());
  const hasTimeInput = hour !== "" || minute !== "";
  const isValidHour = hour.length === 2 && Number(hour) >= 0 && Number(hour) <= 23;
  const isValidMinute =
    minute.length === 2 && Number(minute) >= 0 && Number(minute) <= 59;
  const isTimeValid = !hasTimeInput || (isValidHour && isValidMinute);
  const canSave = Boolean(selectedDate) && isTimeValid;

  const handleSave = () => {
    if (!selectedDate || !canSave) {
      return;
    }

    const datePart = [
      selectedDate.getFullYear(),
      String(selectedDate.getMonth() + 1).padStart(2, "0"),
      String(selectedDate.getDate()).padStart(2, "0"),
    ].join("-");

    const timeValue = hasTimeInput
      ? `${normalizeTimePart(hour)}:${normalizeTimePart(minute)}`
      : "";

    onSave(buildDeadlineDueDate(datePart, timeValue));
  };

  const handleTimeBlur = (setter) => (event) => {
    setter(normalizeTimePart(sanitizeTimePart(event.target.value)));
  };

  return createPortal(
    <motion.div
      ref={pickerRef}
      role="dialog"
      aria-label="Deadline date picker"
      className="date-time-picker"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ type: "spring", stiffness: 420, damping: 32 }}
      style={{
        top: position.top,
        left: position.left,
        visibility: position.ready ? "visible" : "hidden",
        transformOrigin:
          position.placement === "bottom" ? "top left" : "bottom left",
      }}
    >
      <div className="date-time-picker-header">
        <button
          type="button"
          className="date-time-picker-nav"
          aria-label="Previous month"
          onClick={() =>
            setVisibleMonth(
              createDate(
                visibleMonth.getFullYear(),
                visibleMonth.getMonth() - 1,
                1
              )
            )
          }
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <div className="date-time-picker-title">{monthLabel(visibleMonth)}</div>
        <button
          type="button"
          className="date-time-picker-nav"
          aria-label="Next month"
          onClick={() =>
            setVisibleMonth(
              createDate(
                visibleMonth.getFullYear(),
                visibleMonth.getMonth() + 1,
                1
              )
            )
          }
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      </div>

      <div className="date-time-picker-weekdays">
        {WEEKDAY_LABELS.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>

      <div className="date-time-picker-grid">
        {days.map((day) => {
          const isSelected = isSameDate(day, selectedDate);
          const isToday = isSameDate(day, today);
          const isOutsideMonth = day.getMonth() !== visibleMonth.getMonth();

          return (
            <button
              key={day.toISOString()}
              type="button"
              className={[
                "date-time-picker-day",
                isSelected ? "selected" : "",
                isToday ? "today" : "",
                isOutsideMonth ? "outside" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-label={buttonLabel(day)}
              aria-pressed={isSelected}
              onClick={() => setSelectedDate(day)}
            >
              {day.getDate()}
            </button>
          );
        })}
      </div>

      <div className="date-time-picker-time">
        <div className="date-time-picker-time-label">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="9" />
            <polyline points="12 7 12 12 15 15" />
          </svg>
          <span>Optional time</span>
        </div>

        <div className="date-time-picker-time-fields">
          <input
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={2}
            className="date-time-picker-time-input"
            aria-label="Deadline hour"
            placeholder="HH"
            value={hour}
            onChange={(event) => setHour(sanitizeTimePart(event.target.value))}
            onBlur={handleTimeBlur(setHour)}
          />
          <span className="date-time-picker-time-separator">:</span>
          <input
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={2}
            className="date-time-picker-time-input"
            aria-label="Deadline minute"
            placeholder="MM"
            value={minute}
            onChange={(event) => setMinute(sanitizeTimePart(event.target.value))}
            onBlur={handleTimeBlur(setMinute)}
          />
        </div>
      </div>

      <div className="date-time-picker-footer">
        <button
          type="button"
          className="date-time-picker-clear"
          onClick={() => {
            setHour("");
            setMinute("");
          }}
        >
          Clear
        </button>

        <div className="date-time-picker-actions">
          <button
            type="button"
            className="date-time-picker-icon-btn"
            aria-label="Cancel deadline date"
            title="Cancel"
            onClick={onCancel}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>

          <button
            type="button"
            className="date-time-picker-icon-btn confirm"
            aria-label="Save deadline date"
            title="Save"
            disabled={!canSave}
            onClick={handleSave}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </button>
        </div>
      </div>
    </motion.div>,
    document.body
  );
}
