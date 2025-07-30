#!/usr/bin/env python3
"""
Debug script to test SwitchNode evaluation directly.
"""

from kailash.nodes.logic.operations import SwitchNode

def test_switch_direct():
    """Test SwitchNode evaluation directly."""
    
    # Create the region switch from the failing test
    switch = SwitchNode(
        name="region_switch",
        condition_field="region", 
        operator="==", 
        value="US"
    )
    
    # Test with the exact data from the test
    input_data = {"user_type": "premium", "region": "US", "value": 1000}
    
    print("Testing SwitchNode directly:")
    print(f"Input data: {input_data}")
    print(f"Switch condition: region == 'US'")
    print(f"Expected: true_output should have data, false_output should be None")
    
    # Execute the switch using the correct API
    result = switch.execute(input=input_data)
    
    print(f"\nActual result:")
    for key, value in result.items():
        print(f"  {key}: {value}")
        
    # Check what happened
    print(f"\nAnalysis:")
    print(f"  Input region value: '{input_data.get('region')}'")
    print(f"  Expected value: 'US'")
    print(f"  Are they equal? {input_data.get('region') == 'US'}")
    print(f"  true_output is None: {result.get('true_output') is None}")
    print(f"  false_output is None: {result.get('false_output') is None}")
    
    if result.get('true_output') is not None:
        print("✅ Switch correctly evaluated to TRUE")
    else:
        print("❌ Switch incorrectly evaluated to FALSE")

if __name__ == "__main__":
    test_switch_direct()