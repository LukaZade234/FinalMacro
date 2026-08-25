.pragma library

// Stats buckets follow the Mudae daily (00:00 UTC). Live-feed timestamps are
// converted to local time in QML (ActivityLogPanel / RunModel.timeOf).

function pad2(n) {
    return (n < 10 ? "0" : "") + n
}

function remainingSeconds(iso, nowMs) {
    if (!iso)
        return -1
    var ms = Date.parse(iso)
    if (isNaN(ms))
        return -1
    return Math.max(0, Math.floor((ms - (nowMs || Date.now())) / 1000))
}

function livePowerPercent(anchored, updatedAt, maxPower, nowMs) {
    if (anchored === undefined || anchored === null)
        return -1
    var n = Number(anchored)
    if (isNaN(n))
        return -1
    var max = (maxPower !== undefined && maxPower !== null && Number(maxPower) > 0)
        ? Number(maxPower)
        : 155
    var at = Date.parse(updatedAt || "")
    var now = nowMs || Date.now()
    if (!isNaN(at) && now > at)
        n = Math.min(max, n + ((now - at) / 1000 / 180) * 1.0)
    return Math.round(n)
}

function utcDateKey(now) {
    var d = now || new Date()
    return d.getUTCFullYear() + "-" + pad2(d.getUTCMonth() + 1) + "-" + pad2(d.getUTCDate())
}

function utcWeekStartKey(now) {
    var d = now || new Date()
    var offset = (d.getUTCDay() + 6) % 7
    var monday = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - offset))
    return utcDateKey(monday)
}

function utcMonthStartKey(now) {
    var d = now || new Date()
    return d.getUTCFullYear() + "-" + pad2(d.getUTCMonth() + 1) + "-01"
}

function utcYearStartKey(now) {
    var d = now || new Date()
    return d.getUTCFullYear() + "-01-01"
}

function periodKeys(now) {
    var d = now || new Date()
    return {
        today: utcDateKey(d),
        weekStart: utcWeekStartKey(d),
        monthStart: utcMonthStartKey(d),
        yearStart: utcYearStartKey(d)
    }
}

function addDateKey(out, dateKey, amount, periods) {
    if (!dateKey)
        return
    if (dateKey === periods.today)
        out.today += amount
    if (dateKey >= periods.weekStart)
        out.week += amount
    if (dateKey >= periods.monthStart)
        out.month += amount
    if (dateKey >= periods.yearStart)
        out.year += amount
}
