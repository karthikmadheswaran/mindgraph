const DEADLINE_DATE_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?/;

const DEFAULT_DEADLINE_COLOR = { bg: "#d4ddd4", text: "#3a4a3a" };

const startOfDay = (value) => {
  const date = new Date(value);
  date.setHours(0, 0, 0, 0);
  return date;
};

const formatTimeLabel = (hour, minute) =>
  new Date(2000, 0, 1, hour, minute).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });

export const parseDeadlineDate = (dateStr) => {
  if (!dateStr) return null;

  const value = String(dateStr).trim();
  const match = value.match(DEADLINE_DATE_PATTERN);

  if (match) {
    const [, year, month, day, hour = "00", minute = "00"] = match;
    const numericYear = Number(year);
    const numericMonth = Number(month);
    const numericDay = Number(day);
    const numericHour = Number(hour);
    const numericMinute = Number(minute);
    const hasMeaningfulTime = match[4] !== undefined && !(hour === "00" && minute === "00");
    const dateOnly = new Date(numericYear, numericMonth - 1, numericDay);

    return {
      raw: value,
      datePart: `${year}-${month}-${day}`,
      timePart: `${hour}:${minute}`,
      hasMeaningfulTime,
      dateOnly,
      sortValue: `${year}${month}${day}${hour}${minute}`,
      timeLabel: hasMeaningfulTime
        ? formatTimeLabel(numericHour, numericMinute)
        : "",
    };
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }

  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  const hour = String(parsed.getHours()).padStart(2, "0");
  const minute = String(parsed.getMinutes()).padStart(2, "0");
  const hasMeaningfulTime = !(hour === "00" && minute === "00");

  return {
    raw: value,
    datePart: `${year}-${month}-${day}`,
    timePart: `${hour}:${minute}`,
    hasMeaningfulTime,
    dateOnly: startOfDay(parsed),
    sortValue: `${year}${month}${day}${hour}${minute}`,
    timeLabel: hasMeaningfulTime
      ? formatTimeLabel(Number(hour), Number(minute))
      : "",
  };
};

export const deadlineSortValue = (dateStr) =>
  parseDeadlineDate(dateStr)?.sortValue || "";

export const getDeadlineEditorValue = (dateStr) => {
  const parsed = parseDeadlineDate(dateStr);
  return {
    date: parsed?.datePart || "",
    time: parsed?.hasMeaningfulTime ? parsed.timePart : "",
  };
};

export const buildDeadlineDueDate = (dateValue, timeValue = "") => {
  const date = String(dateValue || "").trim();
  if (!date) return "";

  const time = String(timeValue || "").trim();
  return time ? `${date}T${time}` : date;
};

export const deadlineColor = (dateStr) => {
  const parsed = parseDeadlineDate(dateStr);
  if (!parsed) return DEFAULT_DEADLINE_COLOR;

  const today = startOfDay(new Date());
  const days = Math.round((parsed.dateOnly - today) / 86400000);

  if (days <= 1) return { bg: "#c4695a", text: "#fff" };
  if (days <= 3) return { bg: "#d4a574", text: "#3a2a1a" };
  return { bg: "#8a9a7a", text: "#fff" };
};

export const deadlineLabel = (dateStr) => {
  const parsed = parseDeadlineDate(dateStr);
  if (!parsed) return "";

  const today = startOfDay(new Date());
  const days = Math.round((parsed.dateOnly - today) / 86400000);

  let baseLabel = "";
  if (days < 0) {
    baseLabel = "Overdue";
  } else if (days === 0) {
    baseLabel = "Today";
  } else if (days === 1) {
    baseLabel = "Tomorrow";
  } else if (days <= 7) {
    baseLabel = parsed.dateOnly.toLocaleDateString("en", { weekday: "long" });
  } else {
    baseLabel = parsed.dateOnly.toLocaleDateString("en", {
      month: "short",
      day: "numeric",
    });
  }

  if (!parsed.hasMeaningfulTime) {
    return baseLabel;
  }

  return `${baseLabel} · ${parsed.timeLabel}`;
};
