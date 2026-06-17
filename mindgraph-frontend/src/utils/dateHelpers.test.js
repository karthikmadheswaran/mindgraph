import { daysSinceLastMention } from "./dateHelpers";

describe("daysSinceLastMention", () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it("computes whole calendar days from a full ISO timestamp", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-06-17T12:00:00Z"));
    expect(daysSinceLastMention("2026-05-15T11:57:47+00:00")).toBe(33);
  });

  it("treats a date-only string and a full timestamp on the same day identically", () => {
    // The whole point of the accessor: projects.last_mentioned_at (timestamp)
    // and insight.last_mentioned (date-only) must NOT diverge.
    jest.useFakeTimers().setSystemTime(new Date("2026-06-17T12:00:00Z"));
    expect(daysSinceLastMention("2026-05-15")).toBe(
      daysSinceLastMention("2026-05-15T23:00:00Z")
    );
    expect(daysSinceLastMention("2026-05-15")).toBe(33);
  });

  it("returns null for missing or invalid input", () => {
    expect(daysSinceLastMention(null)).toBeNull();
    expect(daysSinceLastMention("")).toBeNull();
    expect(daysSinceLastMention("not-a-date")).toBeNull();
  });

  it("never returns a negative count for a future date", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-06-17T12:00:00Z"));
    expect(daysSinceLastMention("2026-06-20")).toBe(0);
  });
});
