:orphan:

# Unimplemented Nodes Tracker

## Overview

This document tracks placeholder nodes that are referenced in documentation but not yet implemented. These generate Sphinx warnings during documentation builds.

## Current Status (21 Unimplemented Nodes)

### Data Nodes (3)
- [ ] **XMLReader** - Read XML files
  - Priority: Medium
  - Dependencies: lxml or xml.etree
  - Use Case: Configuration files, SOAP responses
  
- [ ] **ParquetReader** - Read Parquet files  
  - Priority: High
  - Dependencies: pyarrow or fastparquet
  - Use Case: Big data, columnar storage
  
- [ ] **ExcelReader** - Read Excel files
  - Priority: High
  - Dependencies: openpyxl or xlrd
  - Use Case: Business data, reports

### Writer Nodes (3)
- [ ] **XMLWriter** - Write XML files
- [ ] **ParquetWriter** - Write Parquet files
- [ ] **ExcelWriter** - Write Excel files

### Database Nodes (2)
- [ ] **MongoDBNode** - MongoDB operations
- [ ] **RedisNode** - Redis cache operations

### API Nodes (3)
- [ ] **WebhookReceiver** - Receive webhook events
- [ ] **OAuth2Client** - OAuth 2.0 authentication
- [ ] **SOAPClient** - SOAP API calls

### Processing Nodes (4)
- [ ] **ImageProcessor** - Image manipulation
- [ ] **AudioProcessor** - Audio file processing
- [ ] **VideoProcessor** - Video file processing
- [ ] **PDFProcessor** - PDF extraction/generation

### Analytics Nodes (3)
- [ ] **StatisticalAnalyzer** - Statistical analysis
- [ ] **TimeSeriesAnalyzer** - Time series analysis
- [ ] **MLModelNode** - Generic ML model runner

### Integration Nodes (3)
- [ ] **SlackNode** - Slack integration
- [ ] **TeamsNode** - Microsoft Teams
- [ ] **EmailNode** - Email sending/receiving

## Implementation Strategy

### Option 1: Remove References (Quick Fix)
Remove these from `docs/api/nodes.rst` until implemented.

### Option 2: Create Placeholder Stubs
Create minimal implementations that raise `NotImplementedError`.

### Option 3: Prioritized Implementation
Implement based on user demand and use cases.

## Recommended Actions

1. **Immediate**: Remove from documentation or add "Coming Soon" note
2. **Short-term**: Implement high-priority nodes (Parquet, Excel)
3. **Long-term**: Full implementation based on roadmap

## Tracking in GitHub

Create issues for each node group:
- #100: Implement additional data readers (XML, Parquet, Excel)
- #101: Implement additional data writers
- #102: Implement database connectors
- #103: Implement advanced processing nodes

## Code Template

```python
@register_node()
class XMLReader(Node):
    """Read XML files into structured data.
    
    Coming Soon: This node is planned for a future release.
    
    Planned Features:
    - XPath support
    - Schema validation
    - Streaming for large files
    - Namespace handling
    """
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to XML file"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError(
            "XMLReader is planned for a future release. "
            "Use JSONReader or TextReader as alternatives."
        )
```