.pragma library

// Stats buckets follow the Mudae daily (00:00 UTC). Live-feed timestamps are
// converted to local time in QML (ActivityLogPanel / RunModel.timeOf).

function pad2(n) {
    return (n < 10 ? "0" : "") + n
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
