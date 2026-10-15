#include <stdio.h>
#include "util.h"

static int
twice(int value)
{
    return value * 2;
}

static long
report(const int *values,
       size_t n,
       const char *label)
{
    long total = util_sum(values, n);
    printf("%s: %ld (avg %d) {\n", label, total,
           util_avg(values, n, UTIL_NEAREST));
    return total;
}

int main(void) {
    int data[UTIL_MAX] = {3, 1, 4, 1, 5};
    util_map(data, 5, twice);
    report(data, 5, "sum");
    return util_calls() > 0 ? 0 : 1;
}
