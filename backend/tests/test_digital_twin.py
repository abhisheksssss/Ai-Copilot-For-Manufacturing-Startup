import asyncio
import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from digital_twin.agent import run_digital_twin_agent


async def test_digital_twin_execution():
    print("Testing Digital Twin Agent Pipeline...")
    query = "Setup an EV Charger assembly unit in Pune with 50,000 monthly units target and 1 Crore budget"
    result = await run_digital_twin_agent(query)
    
    assert "config" in result, "Missing config in response"
    assert "simulation" in result, "Missing simulation in response"
    assert "financials" in result, "Missing financials in response"
    assert "scene" in result, "Missing scene in response"
    assert "summary_text" in result, "Missing summary_text in response"
    
    print("\n✅ DIGITAL TWIN AGENT EXECUTED SUCCESSFULLY!")
    print(f"Product: {result['config']['product']}")
    print(f"Effective Throughput: {result['simulation']['effective_throughput_per_month']} units/month")
    print(f"CAPEX: Rs. {result['financials']['total_capex_inr']/1e7:.2f} Cr")
    print(f"3D Scene Zones: {len(result['scene']['zones'])}")


if __name__ == "__main__":
    asyncio.run(test_digital_twin_execution())
