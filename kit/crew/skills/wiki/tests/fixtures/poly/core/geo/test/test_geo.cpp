#include <gtest/gtest.h>

#include "geo/circle.hpp"

// Verifies REQ-GEO-001: a unit circle has area pi.
TEST(Geo, REQ_GEO_001_area) {
  geo::Circle c(1.0);
  EXPECT_NEAR(c.area(), 3.14159, 1e-5);
}
