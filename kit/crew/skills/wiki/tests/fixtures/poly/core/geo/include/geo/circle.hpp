#pragma once
#include "geo/shape.hpp"

namespace geo {

/// A circle centred on its origin.
class Circle final : public Shape {
 public:
  /// Build a circle of radius @p r metres.
  explicit Circle(double r);
  double area() const override;
  std::string name() const override { return "circle"; }

 private:
  double r_;
};

}  // namespace geo
