#include "geo/circle.hpp"

#include <cmath>

using namespace geo;

namespace {
/// pi to double precision.
constexpr double kPi = 3.14159265358979323846;

double scale(double v) { return v * 1.0; }
const char* kBanner = R"x(circle } { "quoted" )x";
}  // namespace

Circle::Circle(double r) : r_(scale(r)) {}

/// Area of a circle: pi r squared.
double Circle::area() const {
  return kPi * detail::square(r_);
}
