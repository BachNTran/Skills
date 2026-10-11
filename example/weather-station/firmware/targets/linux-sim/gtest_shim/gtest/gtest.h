#pragma once
// Minimal stand-in for the GoogleTest API used by this example (TEST, EXPECT_*, ASSERT_*),
// so the example runs without installing GoogleTest. A real project links GTest instead.
#include <cstdio>
#include <vector>

namespace testing {
struct Case {
  const char* suite;
  const char* name;
  void (*fn)();
};
inline std::vector<Case>& registry() {
  static std::vector<Case> r;
  return r;
}
inline int& failures() {
  static int f = 0;
  return f;
}
struct Registrar {
  Registrar(const char* s, const char* n, void (*fn)()) { registry().push_back({s, n, fn}); }
};
inline void fail(const char* file, int line, const char* expr) {
  std::printf("%s:%d: failure: %s\n", file, line, expr);
  ++failures();
}
}  // namespace testing

#define TEST(suite, name)                                                          \
  static void suite##_##name();                                                    \
  static ::testing::Registrar suite##_##name##_reg(#suite, #name, suite##_##name); \
  static void suite##_##name()

#define EXPECT_TRUE(c) \
  do {                 \
    if (!(c)) ::testing::fail(__FILE__, __LINE__, #c); \
  } while (0)
#define EXPECT_FALSE(c) EXPECT_TRUE(!(c))
#define EXPECT_EQ(a, b) EXPECT_TRUE((a) == (b))
#define ASSERT_TRUE(c)                               \
  do {                                               \
    if (!(c)) {                                      \
      ::testing::fail(__FILE__, __LINE__, #c);       \
      return;                                        \
    }                                                \
  } while (0)
