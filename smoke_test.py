
from core.ml import predict_yield,rank_crops
from core.data import district_climate
from core.resources import calculate_resources
from core.uncertainty import reliability_score

d="Sauran District"; c=district_climate(d)
pred,_=predict_yield(d,"Corn",20,c)
print("Corn predicted yield:",round(pred,2),"centners/ha")
print(rank_crops(d,20,c,["Wheat","Corn","Rice","Cotton","Sunflower","Potato"]).to_string(index=False))
print(calculate_resources(20,100000,10,5000,0.5))
print(reliability_score(exact_location=True,live_climate=False,actual_water=True,actual_energy=True,emission_factor=True,ml_mae=4.0,historical_yield_median=20.0))
