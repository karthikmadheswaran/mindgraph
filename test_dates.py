# test_dates.py
from app.nodes.normalize import resolve_dates
import dateparser

phrases = [
    "next monday",
    "by next monday",
    "this wednesday", 
    "last tuesday",
    "friday",
    "tomorrow",
]


tests = [
    "Need to submit report by next monday and call mom tomorrow",
    "Meeting with Rahul by friday",
    "Finish the deck by this wednesday",
    "Started the project last tuesday",
    "Doctor appointment in 3 days",
]

for t in tests:
    print(f"INPUT:  {t}")
    print(f"OUTPUT: {resolve_dates(t)}")
    print("---")

print("\n=== DATEPARSER DIRECT TEST ===")
for p in phrases:
    result = dateparser.parse(p, settings={'PREFER_DATES_FROM': 'future'})
    print(f"  '{p}' → {result}")

print("=== WITH PARSERS SETTING ===")
for p in phrases:
    result = dateparser.parse(p, settings={
        'PREFER_DATES_FROM': 'future',
        'PARSERS': ['relative-time', 'custom-formats', 'absolute-time', 'base-formats']
    })
    print(f"  '{p}' → {result}")