#!/usr/bin/env python3
"""
Debug script to reproduce the DataFlow model registration endless loop bug.

This script simulates the conditions that cause the endless loop:
1. Registry table creation
2. Multiple model registrations triggering check_checksum → register_model cycles
3. Never reaching application startup
"""

import os
import logging
import time
from dataflow import DataFlow

# Enable debug logging to see the loop in action
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

logger = logging.getLogger(__name__)

def test_model_registry_loop():
    """Test case that reproduces the endless loop bug."""
    
    print("=" * 60)
    print("🐛 REPRODUCING DATAFLOW MODEL REGISTRY ENDLESS LOOP BUG")
    print("=" * 60)
    
    # Use PostgreSQL test database to trigger the real bug conditions
    DATABASE_URL = os.getenv('TEST_DATABASE_URL', 'postgresql://test_user:test_password@localhost:5434/kailash_test')
    
    print(f"📊 Database: {DATABASE_URL}")
    print(f"⏱️  Starting at: {time.strftime('%H:%M:%S')}")
    print()
    
    try:
        # Step 1: Create DataFlow instance (this should be fast)
        print("🔧 Step 1: Creating DataFlow instance...")
        start_time = time.time()
        
        db = DataFlow(
            DATABASE_URL,
            auto_migrate=True,
            existing_schema_mode=False,
            enable_model_persistence=True  # This enables the model registry that causes the bug
        )
        
        creation_time = time.time() - start_time
        print(f"   ✅ DataFlow created in {creation_time:.2f}s")
        print()
        
        # Step 2: Register multiple models (this triggers the bug)
        print("🔧 Step 2: Registering models (this should trigger endless loop)...")
        model_start_time = time.time()
        
        # Monitor how long each model takes to register
        models_to_register = [
            ('User', {'name': str, 'email': str, 'active': bool}),
            ('Session', {'user_id': int, 'token': str, 'expires_at': str}),
            ('Conversation', {'session_id': int, 'title': str, 'created_at': str}),
            ('Message', {'conversation_id': int, 'content': str, 'role': str}),
            ('Settings', {'user_id': int, 'key': str, 'value': str}),
        ]
        
        for i, (model_name, annotations) in enumerate(models_to_register):
            model_register_start = time.time()
            print(f"   📋 Registering {model_name}... ", end='', flush=True)
            
            # Create model class dynamically
            model_class = type(model_name, (), {'__annotations__': annotations})
            
            # This call should complete quickly but will loop endlessly due to the bug
            db.model(model_class)
            
            model_register_time = time.time() - model_register_start
            print(f"took {model_register_time:.2f}s")
            
            # If any model takes more than 10 seconds, it's stuck in the loop
            if model_register_time > 10:
                print(f"   🚨 MODEL {model_name} STUCK IN ENDLESS LOOP!")
                print(f"   ⏱️  Time elapsed: {model_register_time:.2f}s")
                break
            
            # Check total time - if over 30 seconds total, we're definitely in a loop
            total_time = time.time() - model_start_time
            if total_time > 30:
                print(f"   🚨 ENDLESS LOOP DETECTED!")
                print(f"   ⏱️  Total model registration time: {total_time:.2f}s")
                break
        
        total_model_time = time.time() - model_start_time
        print(f"   📊 Total model registration time: {total_model_time:.2f}s")
        print()
        
        # Step 3: Try to reach application startup (this should never happen in the bug)
        print("🔧 Step 3: Checking application startup readiness...")
        startup_check_time = time.time()
        
        # Simulate checking if we can proceed to Nexus initialization
        try:
            models = db.get_models()
            print(f"   ✅ Found {len(models)} registered models: {list(models.keys())}")
            
            # If we get here, the loop bug is NOT happening
            print("   🎉 SUCCESS: No endless loop detected!")
            print("   ✅ Application can proceed to Nexus initialization")
            
        except Exception as e:
            print(f"   ❌ Error during startup check: {e}")
        
        startup_check_duration = time.time() - startup_check_time
        print(f"   ⏱️  Startup check took: {startup_check_duration:.2f}s")
        
    except Exception as e:
        print(f"💥 EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        total_time = time.time() - start_time
        print()
        print("=" * 60)
        print(f"🏁 TOTAL EXECUTION TIME: {total_time:.2f}s")
        print(f"⏱️  Ended at: {time.strftime('%H:%M:%S')}")
        
        if total_time > 60:
            print("🚨 BUG CONFIRMED: Endless loop detected!")
            print("   Expected: ~3-4 seconds for registry + model registration")
            print(f"   Actual: {total_time:.2f} seconds (stuck in loop)")
        else:
            print("✅ BUG NOT REPRODUCED: Registration completed normally")
        
        print("=" * 60)

if __name__ == "__main__":
    test_model_registry_loop()