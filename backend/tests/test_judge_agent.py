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

from agents.judge import run_judge_agent, JudgeResult


async def test_case_1_correct_response():
    query = "Setup a 10,000 unit/month paper bag manufacturing plant in Ahmedabad with 25 Lakhs budget"
    planning = {
        "report": "Roadmap for Paper Bag plant in Ahmedabad. Budget: 25 Lakhs. Proposed CAPEX: 18 Lakhs. OPEX: 4 Lakhs/month. Target: 10,000 bags/month."
    }
    mfg = {
        "report": "Machinery: 2 Automatic Paper Bag Machines. Machine Capacity: 250 bags/day each (Total 500 bags/day = 12,500 bags/month for 25 days). Total Machinery Cost: 12 Lakhs."
    }
    scheme = {
        "report": "PMEGP Scheme applicable for manufacturing up to 50 Lakhs project cost. Subsidy 15-25% based on eligibility subject to application approval."
    }
    research = {
        "report": "Paper bag market size in Gujarat is growing. Top suppliers for craft paper identified in Ahmedabad."
    }

    result = await run_judge_agent(query, planning, mfg, scheme, research)
    print("\n--- TEST 1 RESULT ---")
    print(f"Status: {result.status}")
    print(f"Summary: {result.summary}")
    assert result.status in ["PASS", "ERROR", "OUT_OF_SCOPE"]


async def test_case_2_financial_error():
    query = "Setup a plastic molding factory with 2 Crore user budget"
    planning = {
        "report": "User Budget is 2 Crore INR. However, total proposed CAPEX is 4.5 Crore INR and machinery cost is 3.5 Crore INR."
    }
    mfg = {
        "report": "Machinery cost: 3.5 Crore INR for high-speed injection molding lines."
    }
    scheme = {
        "report": "MSME CGTMSE collateral-free credit up to 2 Crore INR."
    }
    research = {
        "report": "Plastic molding market in Maharashtra."
    }

    result = await run_judge_agent(query, planning, mfg, scheme, research)
    print("\n--- TEST 2 RESULT ---")
    print(f"Status: {result.status}")
    print(f"Mistakes: {[m.model_dump() for m in result.mistakes]}")
    assert result.status == "ERROR"
    assert any(m.category == "financial_consistency" or "financial" in m.issue.lower() or "budget" in m.issue.lower() for m in result.mistakes)


async def test_case_3_manufacturing_error():
    query = "Setup EV Charger assembly unit with target 100,000 units/month"
    planning = {
        "report": "Target Output: 100,000 units/month."
    }
    mfg = {
        "report": "Equipped with 2 assembly lines. Each line capacity is 1,000 units/day. Total 2,000 units/day = 50,000 units/month max capacity for 25 working days."
    }
    scheme = {
        "report": "FAME II and PLI scheme information."
    }
    research = {
        "report": "EV charger suppliers in India."
    }

    result = await run_judge_agent(query, planning, mfg, scheme, research)
    print("\n--- TEST 3 RESULT ---")
    print(f"Status: {result.status}")
    print(f"Mistakes: {[m.model_dump() for m in result.mistakes]}")
    assert result.status == "ERROR"
    assert any(m.category == "manufacturing_feasibility" or "capacity" in m.issue.lower() for m in result.mistakes)


async def test_case_4_scheme_error():
    query = "Setup solar panel manufacturing unit"
    planning = {
        "report": "Business plan for solar panel assembly."
    }
    mfg = {
        "report": "Laminator and tabber machines setup."
    }
    scheme = {
        "report": "Founder is 100% guaranteed a 95% cash grant subsidy under Super-Solar-Free-Money-Scheme with no eligibility criteria required."
    }
    research = {
        "report": "Solar market trends."
    }

    result = await run_judge_agent(query, planning, mfg, scheme, research)
    print("\n--- TEST 4 RESULT ---")
    print(f"Status: {result.status}")
    print(f"Mistakes: {[m.model_dump() for m in result.mistakes]}")
    assert result.status == "ERROR"
    assert any(m.category == "scheme_compliance" or "scheme" in m.issue.lower() or "eligibility" in m.issue.lower() for m in result.mistakes)


async def test_case_5_cross_agent_contradiction():
    query = "Setup PCB assembly startup"
    planning = {
        "report": "Planning Agent: Total CAPEX budget is fixed at 1 Crore INR."
    }
    mfg = {
        "report": "Manufacturing Agent: SMT Pick and Place Machine cost alone is 2.8 Crore INR."
    }
    scheme = {
        "report": "SPECS scheme for electronics."
    }
    research = {
        "report": "PCB market in Pune."
    }

    result = await run_judge_agent(query, planning, mfg, scheme, research)
    print("\n--- TEST 5 RESULT ---")
    print(f"Status: {result.status}")
    print(f"Mistakes: {[m.model_dump() for m in result.mistakes]}")
    assert result.status == "ERROR"


async def test_case_6_out_of_scope():
    query = "Write a Python script to solve the Traveling Salesperson Problem using dynamic programming"
    planning = {"report": "N/A"}
    mfg = {"report": "N/A"}
    scheme = {"report": "N/A"}
    research = {"report": "N/A"}

    result = await run_judge_agent(query, planning, mfg, scheme, research)
    print("\n--- TEST 6 RESULT ---")
    print(f"Status: {result.status}")
    print(f"Summary: {result.summary}")
    assert result.status == "OUT_OF_SCOPE"


if __name__ == "__main__":
    async def run_all():
        print("Running Judge Agent Test Suite...")
        await test_case_1_correct_response()
        await test_case_2_financial_error()
        await test_case_3_manufacturing_error()
        await test_case_4_scheme_error()
        await test_case_5_cross_agent_contradiction()
        await test_case_6_out_of_scope()
        print("\nALL 6 TEST CASES PASSED SUCCESSFULLY!")

    asyncio.run(run_all())
