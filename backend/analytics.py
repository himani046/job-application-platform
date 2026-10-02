from collections import Counter
from datetime import datetime, timezone


def summarize_applications(records):
    total = len(records)
    statuses = Counter(item.status for item in records)
    portals = Counter(item.portal for item in records)
    events = Counter()
    durations = []
    for item in records:
        for event in item.events:
            events[event.get("type", "unknown")] += 1
        try:
            start = datetime.fromisoformat(item.created_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(item.updated_at.replace("Z", "+00:00"))
            durations.append(max(0, (end - start).total_seconds()))
        except (ValueError, TypeError):
            pass
    submitted = statuses.get("submitted", 0)
    return {
        "total": total,
        "by_status": dict(statuses),
        "by_portal": dict(portals),
        "event_counts": dict(events),
        "submitted": submitted,
        "submission_rate": submitted / total if total else 0,
        "average_lifecycle_seconds": sum(durations) / len(durations) if durations else 0,
    }
