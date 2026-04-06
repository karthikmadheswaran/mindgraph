export const deadlineColor = (dateStr) => {
  if (!dateStr) return { bg: "#d4ddd4", text: "#3a4a3a" };
  const days = Math.ceil((new Date(dateStr) - new Date()) / 86400000);
  if (days <= 1) return { bg: "#c4695a", text: "#fff" };
  if (days <= 3) return { bg: "#d4a574", text: "#3a2a1a" };
  return { bg: "#8a9a7a", text: "#fff" };
};

export const deadlineLabel = (dateStr) => {
  if (!dateStr) return "";
  const days = Math.ceil((new Date(dateStr) - new Date()) / 86400000);
  if (days < 0) return "Overdue";
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days <= 7) {
    return new Date(dateStr).toLocaleDateString("en", { weekday: "long" });
  }
  return new Date(dateStr).toLocaleDateString("en", {
    month: "short",
    day: "numeric",
  });
};
