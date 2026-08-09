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

from agents.tools.research_tools import supplier_search


def test_supplier_ranking_pipeline():
    print("Testing Supplier Search Ranking Engine...")
    result = supplier_search.invoke({"product": "milk processing factory", "location": "pune"})
    
    top_suppliers = result.get("top_10_suppliers", [])
    print(f"\nTop Ranked Suppliers Found: {len(top_suppliers)}")
    for i, s in enumerate(top_suppliers, 1):
        print(f"Rank #{i} [Score: {s['score']}]: {s['name']} | Platform: {s['platform']} | Location: {s['location']}")
        print(f"       Snippet: {s['snippet']}")
        
    assert len(top_suppliers) > 0, "No suppliers found"
    
    # Verify that rank #1 is NOT a generic MSME portal
    rank1_name = top_suppliers[0]["name"].lower()
    rank1_snippet = top_suppliers[0]["snippet"].lower()
    
    assert "welcome | msme" not in rank1_name and "ramp portal" not in rank1_name, f"Generic portal ranked #1: {rank1_name}"
    print("\n✅ SUPPLIER RANKING PIPELINE TEST PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_supplier_ranking_pipeline()
