! File: utils_copy.f90
! Purpose: Duplicate file to trigger clone alerts in the static analyzer.
MODULE utils_mod
  IMPLICIT NONE

CONTAINS

  ! Clone type: IDENTICAL (Exact match with utils.f90)
  SUBROUTINE math_util_a(x, y, res)
    REAL, INTENT(IN) :: x, y
    REAL, INTENT(OUT) :: res
    res = x + y
  END SUBROUTINE math_util_a

  ! Clone type: SIMILAR (Same names, only literal 2.0 -> 2.1)
  FUNCTION math_util_b(x) RESULT(val)
    REAL, INTENT(IN) :: x
    REAL :: val
    val = x * x + 2.1 * x
  END FUNCTION math_util_b

  ! Clone type: IDENTICAL (Exact match with utils.f90)
  SUBROUTINE compute_load(force, area, stress)
    REAL, INTENT(IN) :: force, area
    REAL, INTENT(OUT) :: stress
    stress = force / area
  END SUBROUTINE compute_load

  ! Clone type: SIMILAR (Same names, only literal 2.0 -> 2.1)
  FUNCTION calc_growth(rate) RESULT(val)
    REAL, INTENT(IN) :: rate
    REAL :: val
    val = rate * rate + 2.1 * rate
  END FUNCTION calc_growth

  ! Clone type: DIVERGENT (Same interface, completely different logic: loop+IF vs SUM)
  SUBROUTINE calc_metrics(data_array, n, res)
    INTEGER, INTENT(IN) :: n
    REAL, DIMENSION(n), INTENT(IN) :: data_array
    REAL, INTENT(OUT) :: res
    INTEGER :: k
    ! Divergent logic: finds the maximum value using an explicit loop
    res = data_array(1)
    DO k = 2, n
      IF (data_array(k) > res) res = data_array(k)
    END DO
  END SUBROUTINE calc_metrics

END MODULE utils_mod
