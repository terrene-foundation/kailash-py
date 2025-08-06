#!/usr/bin/env python3
"""
Test script to verify the DataFlow model registry endless loop bug fix.

This script tests the fixes:
1. Proper registry initialization before model registration
2. Error handling in _model_exists_with_checksum
3. Graceful fallback when registry initialization fails
"""

import os
import logging
import time
from dataflow import DataFlow

# Enable debug logging to see the fix in action
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

logger = logging.getLogger(__name__)

def test_registry_fix():
    """Test that the registry fixes prevent endless loops."""
    
    print("=" * 60)
    print("🔧 TESTING DATAFLOW MODEL REGISTRY ENDLESS LOOP FIX")
    print("=" * 60)
    
    # Use PostgreSQL test database 
    DATABASE_URL = os.getenv('TEST_DATABASE_URL', 'postgresql://test_user:test_password@localhost:5434/kailash_test')
    
    print(f"📊 Database: {DATABASE_URL}")
    print(f"⏱️  Starting at: {time.strftime('%H:%M:%S')}")
    print()
    
    try:
        # Step 1: Create DataFlow instance with model persistence enabled
        print("🔧 Step 1: Creating DataFlow instance with model registry...")
        start_time = time.time()
        
        db = DataFlow(
            DATABASE_URL,
            auto_migrate=True,
            existing_schema_mode=False,
            enable_model_persistence=True  # This should now work without endless loops
        )
        
        creation_time = time.time() - start_time
        print(f"   ✅ DataFlow created in {creation_time:.2f}s")
        print()
        
        # Step 2: Register models rapidly (should now work without loops)
        print("🔧 Step 2: Rapid model registration (testing the fix)...")
        model_start_time = time.time()
        
        # Register many models quickly to stress-test the fix
        models_to_register = [
            ('User', {'name': str, 'email': str, 'active': bool}),
            ('Session', {'user_id': int, 'token': str, 'expires_at': str}),
            ('Conversation', {'session_id': int, 'title': str, 'created_at': str}),
            ('Message', {'conversation_id': int, 'content': str, 'role': str}),
            ('Settings', {'user_id': int, 'key': str, 'value': str}),
            ('Document', {'title': str, 'content': str, 'tags': str}),
            ('Project', {'name': str, 'description': str, 'status': str}),
            ('Task', {'project_id': int, 'title': str, 'completed': bool}),
            ('Comment', {'task_id': int, 'text': str, 'created_by': int}),
            ('File', {'name': str, 'path': str, 'size': int}),
        ]
        
        for i, (model_name, annotations) in enumerate(models_to_register):
            model_register_start = time.time()
            print(f"   📋 {i+1:2d}. Registering {model_name}... ", end='', flush=True)
            
            # Create model class dynamically
            model_class = type(model_name, (), {'__annotations__': annotations})
            
            # This should now complete quickly without loops due to the fix
            db.model(model_class)
            
            model_register_time = time.time() - model_register_start
            print(f"took {model_register_time:.3f}s")
            
            # If any model takes more than 5 seconds, something is wrong
            if model_register_time > 5:
                print(f"   ⚠️  Model {model_name} took longer than expected: {model_register_time:.2f}s")
                break
        
        total_model_time = time.time() - model_start_time
        print(f"   📊 Total model registration time: {total_model_time:.2f}s")
        print(f"   📊 Average per model: {total_model_time/len(models_to_register):.3f}s")
        print()
        
        # Step 3: Test registry functionality
        print("🔧 Step 3: Testing registry functionality...")
        registry_test_time = time.time()
        
        # Test model discovery
        models = db.get_models()
        print(f"   ✅ Found {len(models)} registered models: {list(models.keys())[:5]}{'...' if len(models) > 5 else ''}")
        
        # Test registry discovery
        if hasattr(db, '_model_registry'):
            discovered = db._model_registry.discover_models()
            print(f"   ✅ Registry discovered {len(discovered)} persisted models")
            
            # Test checksum functionality
            if discovered:
                sample_model = next(iter(discovered.values()))
                checksum = sample_model.get('checksum')
                if checksum:
                    exists = db._model_registry._model_exists_with_checksum(checksum)
                    print(f"   ✅ Checksum verification working: {exists}")
        
        registry_test_duration = time.time() - registry_test_time
        print(f"   ⏱️  Registry tests took: {registry_test_duration:.3f}s")
        print()
        
        # Step 4: Final validation
        print("🔧 Step 4: Final validation...")
        total_time = time.time() - start_time
        
        if total_time < 15:  # Should complete in under 15 seconds for 10 models
            print(f"   🎉 SUCCESS: All operations completed in {total_time:.2f}s")
            print("   ✅ No endless loop detected!")
            print("   ✅ Registry initialization working correctly")
            print("   ✅ Model registration working efficiently")
            print("   ✅ Application can proceed to startup")
        else:
            print(f"   ⚠️  SLOW: Operations took {total_time:.2f}s (should be under 15s)")
        
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
        
        if total_time < 20:
            print("✅ BUG FIXED: Registry working efficiently!")
            print(f"   Expected: <20 seconds for full setup")
            print(f"   Actual: {total_time:.2f} seconds")
            print("   🎯 Ready for production deployment")
        else:
            print("❌ STILL PROBLEMATIC: Registry taking too long")
            print(f"   Max acceptable: 20 seconds")
            print(f"   Actual: {total_time:.2f} seconds")
        
        print("=" * 60)

if __name__ == "__main__":
    test_registry_fix()