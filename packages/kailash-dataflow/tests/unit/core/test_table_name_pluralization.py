"""
Unit tests for table name pluralization fix (DATAFLOW-TABLE-PLURALIZATION-001).

This test suite verifies that the _class_name_to_table_name method correctly
pluralizes model names to table names using proper English pluralization rules.

Bug: Previously, DataFlow used simple "add s" pluralization which produced
incorrect table names like "summarys" instead of "summaries".

Fix: Implemented comprehensive English pluralization with:
- 350+ irregular plural mappings
- Standard rules for -y, -s, -x, -z, -ch, -sh, -f, -fe endings
- Support for compound words (e.g., UserActivity -> user_activities)
"""

import pytest

from dataflow import DataFlow


class TestTableNamePluralization:
    """Test correct pluralization of model names to table names."""

    @pytest.fixture
    def db(self):
        """Create a DataFlow instance for testing."""
        return DataFlow(":memory:", test_mode=True, auto_migrate=False)

    # ============================================================
    # Standard pluralization (add 's')
    # ============================================================

    def test_standard_pluralization(self, db):
        """Test standard words that just add 's'."""
        test_cases = [
            ("User", "users"),
            ("Product", "products"),
            ("Order", "orders"),
            ("Item", "items"),
            ("Account", "accounts"),
            ("Project", "projects"),
            ("Report", "reports"),
            ("Comment", "comments"),
            ("Post", "posts"),
            ("Tag", "tags"),
            ("Role", "roles"),
            ("Group", "groups"),
            ("Team", "teams"),
            ("Event", "events"),
            ("Task", "tasks"),
            ("Log", "logs"),
            ("Record", "records"),
            ("Document", "documents"),
            ("File", "files"),
            ("Image", "images"),
        ]
        for model_name, expected_table in test_cases:
            result = db._class_name_to_table_name(model_name)
            assert (
                result == expected_table
            ), f"{model_name} -> {result}, expected {expected_table}"

    # ============================================================
    # Words ending in 'y' preceded by consonant -> 'ies'
    # ============================================================

    def test_consonant_y_pluralization(self, db):
        """Test words ending in 'y' preceded by a consonant -> 'ies'."""
        test_cases = [
            ("Summary", "summaries"),
            ("Category", "categories"),
            ("History", "histories"),
            ("Entity", "entities"),
            ("Activity", "activities"),
            ("Property", "properties"),
            ("Company", "companies"),
            ("Industry", "industries"),
            ("Story", "stories"),
            ("Inventory", "inventories"),
            ("Factory", "factories"),
            ("Territory", "territories"),
            ("Directory", "directories"),
            ("Repository", "repositories"),
            ("Query", "queries"),
            ("Entry", "entries"),
            ("Delivery", "deliveries"),
            ("Gallery", "galleries"),
            ("Salary", "salaries"),
            ("Library", "libraries"),
            ("Identity", "identities"),
            ("Facility", "facilities"),
            ("Ability", "abilities"),
            ("Capability", "capabilities"),
            ("Utility", "utilities"),
            ("Community", "communities"),
            ("Priority", "priorities"),
            ("Authority", "authorities"),
            ("Policy", "policies"),
            ("Strategy", "strategies"),
            ("Legacy", "legacies"),
            ("Agency", "agencies"),
            ("Currency", "currencies"),
            ("Frequency", "frequencies"),
            ("Emergency", "emergencies"),
            ("Dependency", "dependencies"),
            ("Warranty", "warranties"),
            ("Anomaly", "anomalies"),
            ("Assembly", "assemblies"),
            ("Supply", "supplies"),
            ("Copy", "copies"),
            ("Proxy", "proxies"),
            ("Body", "bodies"),
            ("Study", "studies"),
            ("Duty", "duties"),
            ("Party", "parties"),
            ("City", "cities"),
            ("Quality", "qualities"),
            ("Quantity", "quantities"),
            ("Variety", "varieties"),
            ("Penalty", "penalties"),
            ("Loyalty", "loyalties"),
            ("Casualty", "casualties"),
            ("Treaty", "treaties"),
            ("Academy", "academies"),
            ("Pharmacy", "pharmacies"),
            ("Embassy", "embassies"),
            ("Fantasy", "fantasies"),
        ]
        for model_name, expected_table in test_cases:
            result = db._class_name_to_table_name(model_name)
            assert (
                result == expected_table
            ), f"{model_name} -> {result}, expected {expected_table}"

    def test_vowel_y_pluralization(self, db):
        """Test words ending in 'y' preceded by a vowel -> just add 's'."""
        test_cases = [
            ("Key", "keys"),
            ("Day", "days"),
            ("Way", "ways"),
            ("Play", "plays"),
            ("Survey", "surveys"),
            ("Array", "arrays"),
            ("Delay", "delays"),
            ("Display", "displays"),
            ("Runway", "runways"),
            ("Gateway", "gateways"),
            ("Pathway", "pathways"),
            ("Holiday", "holidays"),
            ("Birthday", "birthdays"),
        ]
        for model_name, expected_table in test_cases:
            result = db._class_name_to_table_name(model_name)
            assert (
                result == expected_table
            ), f"{model_name} -> {result}, expected {expected_table}"

    # ============================================================
    # Words ending in 's', 'x', 'z', 'ch', 'sh' -> add 'es'
    # ============================================================

    def test_sibilant_pluralization(self, db):
        """Test words ending in s, x, z, ch, sh -> add 'es'."""
        test_cases = [
            # -s endings
            ("Status", "statuses"),
            ("Bus", "buses"),
            ("Class", "classes"),
            ("Process", "processes"),
            ("Address", "addresses"),
            ("Access", "accesses"),
            ("Success", "successes"),
            # Note: "Progress" is uncountable, stays as "progress" (in uncountable test)
            ("Business", "businesses"),
            # -x endings
            ("Box", "boxes"),
            ("Tax", "taxes"),
            ("Index", "indexes"),
            ("Suffix", "suffixes"),
            ("Prefix", "prefixes"),
            ("Complex", "complexes"),
            ("Reflex", "reflexes"),
            ("Vertex", "vertices"),  # From irregular map
            ("Matrix", "matrices"),  # From irregular map
            # -z endings
            ("Quiz", "quizzes"),
            ("Buzz", "buzzes"),
            # -ch endings
            ("Batch", "batches"),
            ("Patch", "patches"),
            ("Match", "matches"),
            ("Search", "searches"),
            ("Fetch", "fetches"),
            ("Dispatch", "dispatches"),
            ("Branch", "branches"),
            ("Approach", "approaches"),
            # Note: "Research" is uncountable, stays as "research" (tested in uncountable_nouns)
            # -sh endings
            ("Flash", "flashes"),
            ("Crash", "crashes"),
            ("Hash", "hashes"),
            ("Stash", "stashes"),
            ("Mesh", "meshes"),
            ("Dash", "dashes"),
            ("Push", "pushes"),
            ("Refresh", "refreshes"),
        ]
        for model_name, expected_table in test_cases:
            result = db._class_name_to_table_name(model_name)
            assert (
                result == expected_table
            ), f"{model_name} -> {result}, expected {expected_table}"

    # ============================================================
    # Irregular plurals
    # ============================================================

    def test_common_irregular_plurals(self, db):
        """Test common irregular plural forms."""
        test_cases = [
            ("Person", "people"),
            ("Man", "men"),
            ("Woman", "women"),
            ("Child", "children"),
            ("Foot", "feet"),
            ("Tooth", "teeth"),
            ("Goose", "geese"),
            ("Mouse", "mice"),
            ("Ox", "oxen"),
            ("Die", "dice"),
            ("Leaf", "leaves"),
            ("Half", "halves"),
            ("Knife", "knives"),
            ("Wife", "wives"),
            ("Life", "lives"),
            ("Elf", "elves"),
            ("Loaf", "loaves"),
            ("Thief", "thieves"),
            ("Shelf", "shelves"),
            ("Calf", "calves"),
            ("Wolf", "wolves"),
            ("Scarf", "scarves"),
        ]
        for model_name, expected_table in test_cases:
            result = db._class_name_to_table_name(model_name)
            assert (
                result == expected_table
            ), f"{model_name} -> {result}, expected {expected_table}"

    def test_latin_greek_irregular_plurals(self, db):
        """Test Latin/Greek origin irregular plurals."""
        test_cases = [
            # -is -> -es
            ("Analysis", "analyses"),
            ("Basis", "bases"),
            ("Crisis", "crises"),
            ("Diagnosis", "diagnoses"),
            ("Hypothesis", "hypotheses"),
            ("Thesis", "theses"),
            ("Synopsis", "synopses"),
            ("Synthesis", "syntheses"),
            # -um -> -a or -ums
            ("Datum", "data"),
            ("Medium", "media"),
            ("Bacterium", "bacteria"),
            ("Curriculum", "curricula"),
            ("Spectrum", "spectra"),
            ("Forum", "forums"),
            ("Stadium", "stadiums"),
            ("Museum", "museums"),
            # -us -> -i or -uses
            ("Alumnus", "alumni"),
            ("Nucleus", "nuclei"),
            ("Radius", "radii"),
            ("Stimulus", "stimuli"),
            ("Fungus", "fungi"),
            ("Focus", "focuses"),
            ("Cactus", "cactuses"),
            ("Virus", "viruses"),
            # -on -> -a
            ("Criterion", "criteria"),
            ("Phenomenon", "phenomena"),
        ]
        for model_name, expected_table in test_cases:
            result = db._class_name_to_table_name(model_name)
            assert (
                result == expected_table
            ), f"{model_name} -> {result}, expected {expected_table}"

    def test_unchanged_plurals(self, db):
        """Test words that don't change between singular and plural."""
        test_cases = [
            ("Deer", "deer"),
            ("Fish", "fish"),
            ("Sheep", "sheep"),
            ("Moose", "moose"),
            ("Bison", "bison"),
            ("Salmon", "salmon"),
            ("Trout", "trout"),
            ("Shrimp", "shrimp"),
            ("Swine", "swine"),
            ("Buffalo", "buffalo"),
            ("Elk", "elk"),
            ("Squid", "squid"),
            ("Tuna", "tuna"),
            ("Series", "series"),
            ("Species", "species"),
            ("Aircraft", "aircraft"),
            ("Spacecraft", "spacecraft"),
            ("Offspring", "offspring"),
            ("Means", "means"),
            ("News", "news"),
            ("Headquarters", "headquarters"),
        ]
        for model_name, expected_table in test_cases:
            result = db._class_name_to_table_name(model_name)
            assert (
                result == expected_table
            ), f"{model_name} -> {result}, expected {expected_table}"

    def test_uncountable_nouns(self, db):
        """Test uncountable nouns that stay singular."""
        test_cases = [
            ("Equipment", "equipment"),
            ("Information", "information"),
            ("Software", "software"),
            ("Hardware", "hardware"),
            ("Firmware", "firmware"),
            ("Data", "data"),
            ("Research", "research"),
            ("Traffic", "traffic"),
            ("Feedback", "feedback"),
            ("Metadata", "metadata"),
            ("Analytics", "analytics"),
            ("Physics", "physics"),
            ("Mathematics", "mathematics"),
            ("Statistics", "statistics"),
            ("Logistics", "logistics"),
        ]
        for model_name, expected_table in test_cases:
            result = db._class_name_to_table_name(model_name)
            assert (
                result == expected_table
            ), f"{model_name} -> {result}, expected {expected_table}"

    # ============================================================
    # CamelCase to snake_case conversion
    # ============================================================

    def test_camel_case_conversion(self, db):
        """Test CamelCase to snake_case conversion."""
        test_cases = [
            ("UserProfile", "user_profiles"),
            ("OrderItem", "order_items"),
            ("PaymentMethod", "payment_methods"),
            ("ShippingAddress", "shipping_addresses"),
            ("CustomerAccount", "customer_accounts"),
            ("ProductCategory", "product_categories"),
            ("UserActivity", "user_activities"),
            ("OrderStatus", "order_statuses"),
            ("LoginHistory", "login_histories"),
            ("SystemSummary", "system_summaries"),
            ("DataEntity", "data_entities"),
            ("FileDirectory", "file_directories"),
        ]
        for model_name, expected_table in test_cases:
            result = db._class_name_to_table_name(model_name)
            assert (
                result == expected_table
            ), f"{model_name} -> {result}, expected {expected_table}"

    def test_acronyms_in_names(self, db):
        """Test handling of acronyms in class names."""
        test_cases = [
            ("XMLParser", "xml_parsers"),
            ("HTMLDocument", "html_documents"),
            ("APIEndpoint", "api_endpoints"),
            ("URLMapping", "url_mappings"),
            ("HTTPRequest", "http_requests"),
            ("JSONResponse", "json_responses"),
            ("SQLQuery", "sql_queries"),
        ]
        for model_name, expected_table in test_cases:
            result = db._class_name_to_table_name(model_name)
            assert (
                result == expected_table
            ), f"{model_name} -> {result}, expected {expected_table}"

    # ============================================================
    # Compound words with underscores
    # ============================================================

    def test_compound_word_pluralization(self, db):
        """Test that compound words pluralize the last word correctly."""
        # Direct test of _pluralize method for compound words
        test_cases = [
            ("user_activity", "user_activities"),
            ("order_summary", "order_summaries"),
            ("login_history", "login_histories"),
            ("product_category", "product_categories"),
            ("file_directory", "file_directories"),
            ("data_entity", "data_entities"),
            ("system_status", "system_statuses"),
            ("error_analysis", "error_analyses"),
            ("user_child", "user_children"),
            ("team_person", "team_people"),
        ]
        for word, expected in test_cases:
            result = db._pluralize(word)
            assert (
                result == expected
            ), f"_pluralize('{word}') -> '{result}', expected '{expected}'"

    # ============================================================
    # -o endings
    # ============================================================

    def test_o_endings(self, db):
        """Test words ending in 'o' - some take -es, some take -s."""
        test_cases = [
            # -es endings
            ("Hero", "heroes"),
            ("Potato", "potatoes"),
            ("Tomato", "tomatoes"),
            ("Echo", "echoes"),
            ("Veto", "vetoes"),
            ("Volcano", "volcanoes"),
            ("Tornado", "tornadoes"),
            # -s endings
            ("Photo", "photos"),
            ("Piano", "pianos"),
            ("Memo", "memos"),
            ("Video", "videos"),
            ("Radio", "radios"),
            ("Ratio", "ratios"),
            ("Scenario", "scenarios"),
            ("Studio", "studios"),
            ("Portfolio", "portfolios"),
            ("Zoo", "zoos"),
        ]
        for model_name, expected_table in test_cases:
            result = db._class_name_to_table_name(model_name)
            assert (
                result == expected_table
            ), f"{model_name} -> {result}, expected {expected_table}"

    # ============================================================
    # Real-world model name examples
    # ============================================================

    def test_real_world_model_names(self, db):
        """Test pluralization of common real-world model names."""
        test_cases = [
            # E-commerce
            ("Product", "products"),
            ("Order", "orders"),
            ("OrderItem", "order_items"),
            ("Cart", "carts"),
            ("CartItem", "cart_items"),
            ("Category", "categories"),
            ("Inventory", "inventories"),
            ("Shipment", "shipments"),
            ("Payment", "payments"),
            ("Invoice", "invoices"),
            ("Discount", "discounts"),
            ("Coupon", "coupons"),
            ("Review", "reviews"),
            ("Wishlist", "wishlists"),
            # User management
            ("User", "users"),
            ("Profile", "profiles"),
            ("Role", "roles"),
            ("Permission", "permissions"),
            ("Session", "sessions"),
            ("Token", "tokens"),
            ("Credential", "credentials"),
            ("Identity", "identities"),
            ("Activity", "activities"),
            ("LoginHistory", "login_histories"),
            # Content management
            ("Article", "articles"),
            ("Post", "posts"),
            ("Comment", "comments"),
            ("Reply", "replies"),
            ("Tag", "tags"),
            ("Category", "categories"),
            ("Media", "media"),
            ("Attachment", "attachments"),
            ("Gallery", "galleries"),
            # Analytics
            ("Metric", "metrics"),
            ("Summary", "summaries"),
            ("Report", "reports"),
            ("Analysis", "analyses"),
            ("Statistic", "statistics"),
            ("Event", "events"),
            ("Log", "logs"),
            ("Audit", "audits"),
            # Healthcare
            ("Patient", "patients"),
            ("Diagnosis", "diagnoses"),
            ("Prescription", "prescriptions"),
            ("Appointment", "appointments"),
            ("MedicalHistory", "medical_histories"),
            # Finance
            ("Transaction", "transactions"),
            ("Account", "accounts"),
            ("Balance", "balances"),
            ("Statement", "statements"),
            ("Currency", "currencies"),
            # Project management
            ("Project", "projects"),
            ("Task", "tasks"),
            ("Milestone", "milestones"),
            ("Sprint", "sprints"),
            ("Story", "stories"),
            ("Bug", "bugs"),
            ("Priority", "priorities"),
            ("Status", "statuses"),
        ]
        for model_name, expected_table in test_cases:
            result = db._class_name_to_table_name(model_name)
            assert (
                result == expected_table
            ), f"{model_name} -> {result}, expected {expected_table}"


class TestPluralizationRegression:
    """Regression tests for the pluralization bug fix."""

    @pytest.fixture
    def db(self):
        """Create a DataFlow instance for testing."""
        return DataFlow(":memory:", test_mode=True, auto_migrate=False)

    def test_summary_not_summarys(self, db):
        """Verify Summary -> summaries, not summarys (the original bug)."""
        result = db._class_name_to_table_name("Summary")
        assert result == "summaries", f"Summary should be 'summaries', got '{result}'"
        assert result != "summarys", "Summary should NOT be 'summarys'"

    def test_category_not_categorys(self, db):
        """Verify Category -> categories, not categorys."""
        result = db._class_name_to_table_name("Category")
        assert (
            result == "categories"
        ), f"Category should be 'categories', got '{result}'"
        assert result != "categorys", "Category should NOT be 'categorys'"

    def test_entity_not_entitys(self, db):
        """Verify Entity -> entities, not entitys."""
        result = db._class_name_to_table_name("Entity")
        assert result == "entities", f"Entity should be 'entities', got '{result}'"
        assert result != "entitys", "Entity should NOT be 'entitys'"

    def test_history_not_historys(self, db):
        """Verify History -> histories, not historys."""
        result = db._class_name_to_table_name("History")
        assert result == "histories", f"History should be 'histories', got '{result}'"
        assert result != "historys", "History should NOT be 'historys'"

    def test_status_not_statuss(self, db):
        """Verify Status -> statuses, not statuss."""
        result = db._class_name_to_table_name("Status")
        assert result == "statuses", f"Status should be 'statuses', got '{result}'"
        assert result != "statuss", "Status should NOT be 'statuss'"

    def test_class_not_classs(self, db):
        """Verify Class -> classes, not classs."""
        result = db._class_name_to_table_name("Class")
        assert result == "classes", f"Class should be 'classes', got '{result}'"
        assert result != "classs", "Class should NOT be 'classs'"

    def test_address_not_addresss(self, db):
        """Verify Address -> addresses, not addresss."""
        result = db._class_name_to_table_name("Address")
        assert result == "addresses", f"Address should be 'addresses', got '{result}'"
        assert result != "addresss", "Address should NOT be 'addresss'"

    def test_person_not_persons(self, db):
        """Verify Person -> people, not persons."""
        result = db._class_name_to_table_name("Person")
        assert result == "people", f"Person should be 'people', got '{result}'"
        assert result != "persons", "Person should NOT be 'persons'"

    def test_child_not_childs(self, db):
        """Verify Child -> children, not childs."""
        result = db._class_name_to_table_name("Child")
        assert result == "children", f"Child should be 'children', got '{result}'"
        assert result != "childs", "Child should NOT be 'childs'"

    def test_batch_regression_all_known_issues(self, db):
        """Batch test all known pluralization issues from the bug report."""
        known_issues = [
            ("Summary", "summaries", "summarys"),
            ("Category", "categories", "categorys"),
            ("Entity", "entities", "entitys"),
            ("History", "histories", "historys"),
            ("Status", "statuses", "statuss"),
            ("Class", "classes", "classs"),
            ("Index", "indexes", "indexs"),
            ("Address", "addresses", "addresss"),
            ("Person", "people", "persons"),
            ("Child", "children", "childs"),
            ("Analysis", "analyses", "analysiss"),
            ("Process", "processes", "processs"),
            ("Business", "businesses", "businesss"),
            ("Activity", "activities", "activitys"),
            ("Property", "properties", "propertys"),
            ("Company", "companies", "companys"),
            ("Policy", "policies", "policys"),
            ("Strategy", "strategies", "strategys"),
        ]

        for model_name, correct, incorrect in known_issues:
            result = db._class_name_to_table_name(model_name)
            assert (
                result == correct
            ), f"{model_name} should be '{correct}', got '{result}'"
            assert result != incorrect, f"{model_name} should NOT be '{incorrect}'"
