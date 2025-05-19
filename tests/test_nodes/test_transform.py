"""Tests for transform processor nodes."""

import pytest
from typing import Dict, Any

from kailash.nodes.transform.processors import (
    Filter,
    Map,
    Sort
)
from kailash.sdk_exceptions import NodeValidationError, NodeExecutionError


class TestFilterNode:
    """Test filter transformation node."""
    
    def test_filter_with_expression(self):
        """Test filtering with lambda expression."""
        node = FilterNode(node_id="filter", name="Filter Node")
        
        data = [1, 2, 3, 4, 5]
        result = node.execute({
            "data": data,
            "expression": "lambda x: x > 3"
        })
        
        assert result["filtered_data"] == [4, 5]
    
    def test_filter_with_custom_field(self):
        """Test filtering on custom field."""
        node = FilterNode(node_id="filter", name="Filter Node")
        
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 35}
        ]
        
        result = node.execute({
            "data": data,
            "expression": "lambda x: x['age'] > 30",
            "field": "age"
        })
        
        assert len(result["filtered_data"]) == 1
        assert result["filtered_data"][0]["name"] == "Charlie"
    
    def test_filter_empty_data(self):
        """Test filtering empty data."""
        node = FilterNode(node_id="filter", name="Filter Node")
        
        result = node.execute({
            "data": [],
            "expression": "lambda x: x > 0"
        })
        
        assert result["filtered_data"] == []
    
    def test_filter_invalid_expression(self):
        """Test filtering with invalid expression."""
        node = FilterNode(node_id="filter", name="Filter Node")
        
        with pytest.raises(KailashRuntimeError):
            node.execute({
                "data": [1, 2, 3],
                "expression": "invalid python code"
            })
    
    def test_filter_expression_error(self):
        """Test filtering when expression raises error."""
        node = FilterNode(node_id="filter", name="Filter Node")
        
        with pytest.raises(KailashRuntimeError):
            node.execute({
                "data": [1, 2, "three"],
                "expression": "lambda x: x > 2"  # Will fail on "three"
            })


class TestMapNode:
    """Test map transformation node."""
    
    def test_map_simple_transformation(self):
        """Test simple mapping operation."""
        node = MapNode(node_id="map", name="Map Node")
        
        data = [1, 2, 3, 4]
        result = node.execute({
            "data": data,
            "expression": "lambda x: x * 2"
        })
        
        assert result["mapped_data"] == [2, 4, 6, 8]
    
    def test_map_dict_transformation(self):
        """Test mapping on dictionaries."""
        node = MapNode(node_id="map", name="Map Node")
        
        data = [
            {"value": 10},
            {"value": 20},
            {"value": 30}
        ]
        
        result = node.execute({
            "data": data,
            "expression": "lambda x: {'value': x['value'], 'doubled': x['value'] * 2}"
        })
        
        assert len(result["mapped_data"]) == 3
        assert result["mapped_data"][0]["doubled"] == 20
        assert result["mapped_data"][1]["doubled"] == 40
    
    def test_map_with_complex_expression(self):
        """Test mapping with complex expression."""
        node = MapNode(node_id="map", name="Map Node")
        
        data = ["hello", "world", "python"]
        result = node.execute({
            "data": data,
            "expression": "lambda x: {'original': x, 'upper': x.upper(), 'length': len(x)}"
        })
        
        assert result["mapped_data"][0]["upper"] == "HELLO"
        assert result["mapped_data"][2]["length"] == 6
    
    def test_map_empty_data(self):
        """Test mapping empty data."""
        node = MapNode(node_id="map", name="Map Node")
        
        result = node.execute({
            "data": [],
            "expression": "lambda x: x + 1"
        })
        
        assert result["mapped_data"] == []
    
    def test_map_invalid_expression(self):
        """Test mapping with invalid expression."""
        node = MapNode(node_id="map", name="Map Node")
        
        with pytest.raises(KailashRuntimeError):
            node.execute({
                "data": [1, 2, 3],
                "expression": "not valid python"
            })


class TestReduceNode:
    """Test reduce transformation node."""
    
    def test_reduce_sum(self):
        """Test reduce operation for sum."""
        node = ReduceNode(node_id="reduce", name="Reduce Node")
        
        data = [1, 2, 3, 4, 5]
        result = node.execute({
            "data": data,
            "expression": "lambda acc, x: acc + x",
            "initial_value": 0
        })
        
        assert result["reduced_value"] == 15
    
    def test_reduce_product(self):
        """Test reduce operation for product."""
        node = ReduceNode(node_id="reduce", name="Reduce Node")
        
        data = [2, 3, 4]
        result = node.execute({
            "data": data,
            "expression": "lambda acc, x: acc * x",
            "initial_value": 1
        })
        
        assert result["reduced_value"] == 24
    
    def test_reduce_string_concatenation(self):
        """Test reduce with string concatenation."""
        node = ReduceNode(node_id="reduce", name="Reduce Node")
        
        data = ["Hello", " ", "World"]
        result = node.execute({
            "data": data,
            "expression": "lambda acc, x: acc + x",
            "initial_value": ""
        })
        
        assert result["reduced_value"] == "Hello World"
    
    def test_reduce_dict_aggregation(self):
        """Test reduce with dictionary aggregation."""
        node = ReduceNode(node_id="reduce", name="Reduce Node")
        
        data = [
            {"value": 10},
            {"value": 20},
            {"value": 30}
        ]
        
        result = node.execute({
            "data": data,
            "expression": "lambda acc, x: acc + x['value']",
            "initial_value": 0
        })
        
        assert result["reduced_value"] == 60
    
    def test_reduce_empty_data(self):
        """Test reduce with empty data."""
        node = ReduceNode(node_id="reduce", name="Reduce Node")
        
        result = node.execute({
            "data": [],
            "expression": "lambda acc, x: acc + x",
            "initial_value": 100
        })
        
        assert result["reduced_value"] == 100
    
    def test_reduce_no_initial_value(self):
        """Test reduce without initial value."""
        node = ReduceNode(node_id="reduce", name="Reduce Node")
        
        data = [1, 2, 3]
        result = node.execute({
            "data": data,
            "expression": "lambda acc, x: acc + x"
        })
        
        assert result["reduced_value"] == 6


class TestSortNode:
    """Test sort transformation node."""
    
    def test_sort_numbers_ascending(self):
        """Test sorting numbers in ascending order."""
        node = SortNode(node_id="sort", name="Sort Node")
        
        data = [3, 1, 4, 1, 5, 9, 2, 6]
        result = node.execute({"data": data})
        
        assert result["sorted_data"] == [1, 1, 2, 3, 4, 5, 6, 9]
    
    def test_sort_numbers_descending(self):
        """Test sorting numbers in descending order."""
        node = SortNode(node_id="sort", name="Sort Node")
        
        data = [3, 1, 4, 1, 5]
        result = node.execute({
            "data": data,
            "reverse": True
        })
        
        assert result["sorted_data"] == [5, 4, 3, 1, 1]
    
    def test_sort_strings(self):
        """Test sorting strings."""
        node = SortNode(node_id="sort", name="Sort Node")
        
        data = ["banana", "apple", "cherry", "date"]
        result = node.execute({"data": data})
        
        assert result["sorted_data"] == ["apple", "banana", "cherry", "date"]
    
    def test_sort_with_key_function(self):
        """Test sorting with key function."""
        node = SortNode(node_id="sort", name="Sort Node")
        
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 35}
        ]
        
        result = node.execute({
            "data": data,
            "key": "lambda x: x['age']"
        })
        
        assert result["sorted_data"][0]["name"] == "Bob"
        assert result["sorted_data"][2]["name"] == "Charlie"
    
    def test_sort_with_complex_key(self):
        """Test sorting with complex key."""
        node = SortNode(node_id="sort", name="Sort Node")
        
        data = ["aa", "b", "ccc", "dddd"]
        result = node.execute({
            "data": data,
            "key": "lambda x: len(x)"
        })
        
        assert result["sorted_data"] == ["b", "aa", "ccc", "dddd"]
    
    def test_sort_empty_data(self):
        """Test sorting empty data."""
        node = SortNode(node_id="sort", name="Sort Node")
        
        result = node.execute({"data": []})
        assert result["sorted_data"] == []
    
    def test_sort_invalid_key(self):
        """Test sorting with invalid key function."""
        node = SortNode(node_id="sort", name="Sort Node")
        
        with pytest.raises(KailashRuntimeError):
            node.execute({
                "data": [1, 2, 3],
                "key": "invalid python"
            })


class TestGroupByNode:
    """Test group by transformation node."""
    
    def test_group_by_simple_key(self):
        """Test grouping by simple key."""
        node = GroupByNode(node_id="group", name="Group Node")
        
        data = [
            {"category": "A", "value": 10},
            {"category": "B", "value": 20},
            {"category": "A", "value": 30},
            {"category": "B", "value": 40}
        ]
        
        result = node.execute({
            "data": data,
            "key_expression": "lambda x: x['category']"
        })
        
        grouped = result["grouped_data"]
        assert "A" in grouped
        assert "B" in grouped
        assert len(grouped["A"]) == 2
        assert len(grouped["B"]) == 2
    
    def test_group_by_computed_key(self):
        """Test grouping by computed key."""
        node = GroupByNode(node_id="group", name="Group Node")
        
        data = [1, 2, 3, 4, 5, 6, 7, 8]
        result = node.execute({
            "data": data,
            "key_expression": "lambda x: 'even' if x % 2 == 0 else 'odd'"
        })
        
        grouped = result["grouped_data"]
        assert len(grouped["even"]) == 4
        assert len(grouped["odd"]) == 4
        assert 2 in grouped["even"]
        assert 3 in grouped["odd"]
    
    def test_group_by_multiple_attributes(self):
        """Test grouping by multiple attributes."""
        node = GroupByNode(node_id="group", name="Group Node")
        
        data = [
            {"dept": "IT", "level": "senior", "name": "Alice"},
            {"dept": "IT", "level": "junior", "name": "Bob"},
            {"dept": "HR", "level": "senior", "name": "Charlie"},
            {"dept": "IT", "level": "senior", "name": "David"}
        ]
        
        result = node.execute({
            "data": data,
            "key_expression": "lambda x: (x['dept'], x['level'])"
        })
        
        grouped = result["grouped_data"]
        it_senior_key = str(("IT", "senior"))
        assert it_senior_key in grouped
        assert len(grouped[it_senior_key]) == 2
    
    def test_group_by_empty_data(self):
        """Test grouping empty data."""
        node = GroupByNode(node_id="group", name="Group Node")
        
        result = node.execute({
            "data": [],
            "key_expression": "lambda x: x"
        })
        
        assert result["grouped_data"] == {}
    
    def test_group_by_invalid_expression(self):
        """Test grouping with invalid expression."""
        node = GroupByNode(node_id="group", name="Group Node")
        
        with pytest.raises(KailashRuntimeError):
            node.execute({
                "data": [1, 2, 3],
                "key_expression": "not valid"
            })


class TestJoinNode:
    """Test join transformation node."""
    
    def test_inner_join(self):
        """Test inner join operation."""
        node = JoinNode(node_id="join", name="Join Node")
        
        left_data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
            {"id": 3, "name": "Charlie"}
        ]
        
        right_data = [
            {"id": 1, "dept": "IT"},
            {"id": 2, "dept": "HR"},
            {"id": 4, "dept": "Sales"}
        ]
        
        result = node.execute({
            "left_data": left_data,
            "right_data": right_data,
            "left_key": "id",
            "right_key": "id",
            "join_type": "inner"
        })
        
        joined = result["joined_data"]
        assert len(joined) == 2
        assert {"id": 1, "name": "Alice", "dept": "IT"} in joined
        assert {"id": 2, "name": "Bob", "dept": "HR"} in joined
    
    def test_left_join(self):
        """Test left join operation."""
        node = JoinNode(node_id="join", name="Join Node")
        
        left_data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
            {"id": 3, "name": "Charlie"}
        ]
        
        right_data = [
            {"id": 1, "dept": "IT"},
            {"id": 3, "dept": "HR"}
        ]
        
        result = node.execute({
            "left_data": left_data,
            "right_data": right_data,
            "left_key": "id",
            "right_key": "id",
            "join_type": "left"
        })
        
        joined = result["joined_data"]
        assert len(joined) == 3
        
        # Bob should have None for dept
        bob_record = next(r for r in joined if r["name"] == "Bob")
        assert bob_record["dept"] is None
    
    def test_right_join(self):
        """Test right join operation."""
        node = JoinNode(node_id="join", name="Join Node")
        
        left_data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ]
        
        right_data = [
            {"id": 2, "dept": "HR"},
            {"id": 3, "dept": "Sales"},
            {"id": 4, "dept": "IT"}
        ]
        
        result = node.execute({
            "left_data": left_data,
            "right_data": right_data,
            "left_key": "id",
            "right_key": "id",
            "join_type": "right"
        })
        
        joined = result["joined_data"]
        assert len(joined) == 3
        
        # Sales and IT records should have None for name
        sales_record = next(r for r in joined if r["dept"] == "Sales")
        assert sales_record["name"] is None
    
    def test_join_with_different_key_names(self):
        """Test join with different key names."""
        node = JoinNode(node_id="join", name="Join Node")
        
        left_data = [
            {"user_id": 1, "name": "Alice"},
            {"user_id": 2, "name": "Bob"}
        ]
        
        right_data = [
            {"employee_id": 1, "salary": 50000},
            {"employee_id": 2, "salary": 60000}
        ]
        
        result = node.execute({
            "left_data": left_data,
            "right_data": right_data,
            "left_key": "user_id",
            "right_key": "employee_id",
            "join_type": "inner"
        })
        
        joined = result["joined_data"]
        assert len(joined) == 2
        assert joined[0]["name"] == "Alice"
        assert joined[0]["salary"] == 50000
    
    def test_join_empty_data(self):
        """Test join with empty data."""
        node = JoinNode(node_id="join", name="Join Node")
        
        result = node.execute({
            "left_data": [],
            "right_data": [{"id": 1, "value": 100}],
            "left_key": "id",
            "right_key": "id",
            "join_type": "inner"
        })
        
        assert result["joined_data"] == []
    
    def test_join_invalid_type(self):
        """Test join with invalid join type."""
        node = JoinNode(node_id="join", name="Join Node")
        
        with pytest.raises(KailashValidationError):
            node.execute({
                "left_data": [{"id": 1}],
                "right_data": [{"id": 1}],
                "left_key": "id",
                "right_key": "id",
                "join_type": "invalid"
            })


class TestAggregateNode:
    """Test aggregate transformation node."""
    
    def test_aggregate_sum(self):
        """Test sum aggregation."""
        node = AggregateNode(node_id="agg", name="Aggregate Node")
        
        data = [1, 2, 3, 4, 5]
        result = node.execute({
            "data": data,
            "operation": "sum"
        })
        
        assert result["aggregated_value"] == 15
    
    def test_aggregate_mean(self):
        """Test mean aggregation."""
        node = AggregateNode(node_id="agg", name="Aggregate Node")
        
        data = [10, 20, 30, 40]
        result = node.execute({
            "data": data,
            "operation": "mean"
        })
        
        assert result["aggregated_value"] == 25
    
    def test_aggregate_count(self):
        """Test count aggregation."""
        node = AggregateNode(node_id="agg", name="Aggregate Node")
        
        data = ["a", "b", "c", "d", "e"]
        result = node.execute({
            "data": data,
            "operation": "count"
        })
        
        assert result["aggregated_value"] == 5
    
    def test_aggregate_min_max(self):
        """Test min and max aggregation."""
        node = AggregateNode(node_id="agg", name="Aggregate Node")
        
        data = [5, 2, 8, 1, 9, 3]
        
        # Test min
        result_min = node.execute({
            "data": data,
            "operation": "min"
        })
        assert result_min["aggregated_value"] == 1
        
        # Test max
        result_max = node.execute({
            "data": data,
            "operation": "max"
        })
        assert result_max["aggregated_value"] == 9
    
    def test_aggregate_with_field(self):
        """Test aggregation on specific field."""
        node = AggregateNode(node_id="agg", name="Aggregate Node")
        
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 35}
        ]
        
        result = node.execute({
            "data": data,
            "operation": "mean",
            "field": "age"
        })
        
        assert result["aggregated_value"] == 30
    
    def test_aggregate_empty_data(self):
        """Test aggregation on empty data."""
        node = AggregateNode(node_id="agg", name="Aggregate Node")
        
        result = node.execute({
            "data": [],
            "operation": "sum"
        })
        
        assert result["aggregated_value"] == 0
    
    def test_aggregate_invalid_operation(self):
        """Test aggregation with invalid operation."""
        node = AggregateNode(node_id="agg", name="Aggregate Node")
        
        with pytest.raises(KailashValidationError):
            node.execute({
                "data": [1, 2, 3],
                "operation": "invalid"
            })
    
    def test_aggregate_non_numeric_mean(self):
        """Test mean aggregation on non-numeric data."""
        node = AggregateNode(node_id="agg", name="Aggregate Node")
        
        with pytest.raises(KailashRuntimeError):
            node.execute({
                "data": ["a", "b", "c"],
                "operation": "mean"
            })