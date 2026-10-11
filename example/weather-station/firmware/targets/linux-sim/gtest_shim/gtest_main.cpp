#include "gtest/gtest.h"

int main() {
  int failed_cases = 0;
  for (const auto& c : testing::registry()) {
    const int before = testing::failures();
    c.fn();
    const bool ok = testing::failures() == before;
    failed_cases += ok ? 0 : 1;
    std::printf("[ %s ] %s.%s\n", ok ? "    OK" : "FAILED", c.suite, c.name);
  }
  const int n = static_cast<int>(testing::registry().size());
  std::printf("%d tests, %d passed, %d failed\n", n, n - failed_cases, failed_cases);
  return failed_cases == 0 ? 0 : 1;
}
