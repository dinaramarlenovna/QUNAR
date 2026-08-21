
# Scientific status - v0.1

Current best model: Random Forest

Out-of-time validation (train <=2019; test 2020-2023):
            model  MAE_centners_ha  RMSE_centners_ha       R2  MAPE_percent
    Random Forest        14.260431         26.258972 0.842787     24.357401
            Ridge        17.188449         28.234032 0.818248     39.750846
Gradient Boosting        15.495966         28.721239 0.811921     27.484716

Important:
- The ML layer predicts crop yield; it does NOT yet claim full natural-resource efficiency.
- The reliability score is a data-completeness indicator, not a statistical confidence interval.
- Otyrar District has climate fallback but is not represented in the current crop-yield inferential panel; its district categorical effect is therefore unseen by the model.
- WaPOR field extraction is reserved for v0.2 until the exact adapter is implemented and tested.
