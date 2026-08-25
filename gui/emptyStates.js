.pragma library

// Copy for empty lists and charts. ``connected`` is App.connected; ``hasAnyEntries``
// means the log has rows before filters (not “shown count is zero”).

function statsLogEmpty(connected, hasAnyEntries, what) {
    if (hasAnyEntries)
        return "No entries match the current filters."
    if (!connected)
        return "Not connected — connect on Run to record " + what + "."
    return "Nothing recorded yet — roll, react, or play minigames while connected to log " + what + "."
}

function statsBreakdownEmpty(connected, hasAnyEntries) {
    if (hasAnyEntries)
        return "No data for the current filters."
    if (!connected)
        return "Not connected — connect on Run first."
    return "Nothing recorded yet — activity on Run will populate this."
}

function chartRangeEmpty(connected, hasAnyEntries, noun) {
    if (!hasAnyEntries) {
        if (!connected)
            return "Not connected — connect on Run to record " + noun + "."
        return "Nothing recorded yet — " + noun + " appear after activity on Run."
    }
    return "No " + noun + " in this date range."
}

function runFeedEmpty(connected) {
    if (!connected)
        return "Not connected — connect to see live activity."
    return "Waiting for Mudae in this channel."
}

function activityLogEmpty(connected, hasAnyEntries) {
    if (!hasAnyEntries) {
        if (!connected)
            return "Not connected — connect to see activity here."
        return "Waiting for Mudae in this channel."
    }
    return "No lines match this filter."
}

function soulmateChartEmpty(connected, hasAnyEntries) {
    if (!hasAnyEntries) {
        if (!connected)
            return "Not connected — connect on Run to record soulmates."
        return "Nothing recorded yet — rolls while connected log soulmates here."
    }
    return "No data for this view."
}
