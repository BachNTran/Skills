#include "util.h"

static int calls = 0;

/* helper: absolute value */
static int abs_i(int v) { return v < 0 ? -v : v; }

long util_sum(const int *values, size_t n) {
    long total = 0;
    calls++;
    for (size_t i = 0; i < n; i++) total += values[i];
    return total;
}

/**
 * Average with explicit rounding.
 * @see util_sum
 * @see Nowhere
 */
int util_avg(const int *values, size_t n, enum util_round mode) {
    if (n == 0) return 0;
    long s = util_sum(values, n);
    if (mode == UTIL_NEAREST) return (int)((s + (long)n / 2) / (long)n);
    return (int)(s / (long)n);
}

void util_map(int *values, size_t n, util_fn fn) {
    for (size_t i = 0; i < n; i++) {
        values[i] = fn(abs_i(values[i]));
    }
}

int util_calls(void) { return calls; }
