# District × crop update to 2025

The calibrated crop ML panel was extended with official district × crop observations for 2024 and 2025.

- Agricultural source: Bureau of National Statistics workbook `61-РУС-ДИНАМИКА растениеводства 1990-2025г.г.(1).xlsx`.
- District-level fields used: sown area and yield for Wheat, Corn, Rice, Cotton, Sunflower and Potato.
- Climate source: `MASTER_панель_Туркестан_2004_2025_NASA_v2.xlsx`, NASA POWER, annual and April-September indicators.
- New rows appended: 139 (68 for 2024; 71 for 2025).
- Final analytical panel: 1362 rows, 17 districts, 6 calibrated crops, 2004-2025.
- Only rows with numeric positive district crop area, numeric positive district crop yield, and complete district-year climate inputs were included. Missing official markers (`-`, `..`) were not converted to zero.
- Gross harvest was used as a consistency audit where a numeric district value was available; the official area and yield fields remain the direct ML inputs/target.
