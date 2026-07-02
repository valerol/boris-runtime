from fastapi import FastAPI
from kernel.runtime import BORISKernel

app = FastAPI()
kernel = BORISKernel()

@app.post("/event")
def event(req: dict):
    return kernel.run(req)
