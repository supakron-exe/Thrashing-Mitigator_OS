from collections import defaultdict


def compact_series(points, limit=1000):
    """Preserve min/max and segment gaps rather than averaging away spikes."""
    if len(points) <= limit:
        return points
    size = max(1, (len(points) + limit // 4 - 1) // (limit // 4))
    result = []
    for offset in range(0, len(points), size):
        chunk = points[offset:offset+size]
        segments = defaultdict(list)
        for point in chunk:
            segments[point['segment']].append(point)
        for items in segments.values():
            lo = min(items, key=lambda p: p['percent'])
            hi = max(items, key=lambda p: p['percent'])
            result.extend(sorted({p['timestamp']: p for p in (items[0], lo, hi, items[-1])}.values(), key=lambda p:p['timestamp']))
    return result


def app_summary(rows):
    first, last = rows[0], rows[-1]
    valid = len(rows) > 1 and all(r['complete'] for r in rows) and first['segment'] == last['segment']
    return dict(id=last['id'], name=last['name'], bytes=last['rss'] if last['complete'] else None,
                before=first['rss'] if first['complete'] else None, delta=last['rss']-first['rss'] if valid else None,
                peak=max(r['peak'] for r in rows), count=last['count'], complete=all(r['complete'] for r in rows),
                firstAt=first['timestamp'], lastAt=last['timestamp'], closed=last['count']==0)
