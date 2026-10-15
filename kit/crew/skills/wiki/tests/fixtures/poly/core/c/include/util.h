/**
 * @file util.h
 * @brief Small numeric helpers shared by the core modules.
 */
#ifndef UTIL_H
#define UTIL_H

#include <stddef.h>

/** Maximum number of samples a buffer holds. */
#define UTIL_MAX 64

/// Clamp v into [lo, hi].
#define UTIL_CLAMP(v, lo, hi) ((v) < (lo) ? (lo) : ((v) > (hi) ? (hi) : (v)))

/**
 * @brief A running sum over integer samples.
 */
struct util_acc {
    long total;  //!< sum of every sample added
    int count;   //!< number of samples added
};

/// Callback applied to each sample.
typedef int (*util_fn)(int value);

/** Rounding mode for util_avg(). */
enum util_round { UTIL_DOWN, UTIL_NEAREST };

/**
 * @brief Sum the first @p n values.
 * @param values pointer to the samples
 * @param n number of samples to read
 * @return the sum, 0 when @p n is 0
 */
long util_sum(const int *values, size_t n);

/// Average of the first n values, rounded per mode.
/// @param values pointer to the samples
/// @param n number of samples
/// @param mode rounding mode
int util_avg(const int *values, size_t n, enum util_round mode);

/** Apply @p fn to every value in place. @see util_sum */
void util_map(int *values, size_t n, util_fn fn);

/* Number of calls made so far (a plain comment still counts as a doc). */
extern int util_calls(void);

extern int util_debug_level;

#endif /* UTIL_H */
