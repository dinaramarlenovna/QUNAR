import tempfile
import unittest
from pathlib import Path
from core.yield_reference import trailing_three_year_yield


class YieldReferenceTests(unittest.TestCase):
    def make(self, lines):
        f = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.csv', delete=False)
        f.write('District,Crop,Year,"Yield, centners/ha"\n')
        f.write('\n'.join(lines))
        f.close()
        self.addCleanup(Path(f.name).unlink)
        return f.name

    def test_strict_prior_years_and_no_cross_crop(self):
        f=self.make(['A,Corn,2022,50','A,Corn,2023,10','A,Corn,2024,20',
                     'A,Corn,2025,30','A,Corn,2026,900','A,Wheat,2025,800','B,Corn,2025,900'])
        r=trailing_three_year_yield(f,'A','Corn',2026)
        self.assertEqual(r.years,(2023,2024,2025))
        self.assertAlmostEqual(r.value_c_ha,20)
        self.assertAlmostEqual(trailing_three_year_yield(f,'A','Corn',2025).value_c_ha,80/3)

    def test_missing_year_not_silently_backfilled(self):
        f=self.make(['A,Corn,2021,10','A,Corn,2023,20','A,Corn,2025,40'])
        r=trailing_three_year_yield(f,'A','Corn',2026)
        self.assertEqual(r.years,(2023,2025))
        self.assertEqual(r.value_c_ha,30)
        self.assertIn('Only 2',r.warning)

    def test_missing_does_not_return_zero(self):
        f=self.make(['A,Corn,2025,0','B,Corn,2024,14'])
        self.assertIsNone(trailing_three_year_yield(f,'A','Corn',2026).value_c_ha)

    def test_duplicate_year_rejected(self):
        f=self.make(['A,Corn,2025,25','A,Corn,2025,30'])
        with self.assertRaises(ValueError):
            trailing_three_year_yield(f,'A','Corn',2026)

if __name__=='__main__':unittest.main()
