# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
CARE-012: Merkle Tree Audit Verification.

Provides Merkle tree implementation for efficient audit log verification.
Enables proving an individual audit entry exists without revealing the entire log.

Key Features:
- O(log n) proof generation
- O(log n) proof verification
- Tamper detection for individual entries
- Integration with AuditRecord integrity hashes

Example:
    from eatp.merkle import MerkleTree, verify_merkle_proof

    # Build tree from audit records
    tree = MerkleTree.from_audit_records(records)

    # Generate proof for a specific entry
    proof = tree.generate_proof(index=5)

    # Verify proof without needing full tree
    is_valid = verify_merkle_proof(leaf_hash, proof)
"""

import hashlib
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from eatp.audit_store import AuditRecord


@dataclass
class MerkleNode:
    """
    A node in the Merkle tree.

    Leaf nodes contain data_index pointing to the original data.
    Internal nodes combine two child nodes.

    Attributes:
        hash: SHA-256 hash of this node
        left: Left child node (None for leaf nodes)
        right: Right child node (None for leaf nodes)
        data_index: Index into original data (set only for leaf nodes)
    """

    hash: str
    left: Optional["MerkleNode"] = None
    right: Optional["MerkleNode"] = None
    data_index: Optional[int] = None

    def is_leaf(self) -> bool:
        """Check if this is a leaf node."""
        return self.data_index is not None


@dataclass
class MerkleProof:
    """
    Proof of inclusion for a leaf in a Merkle tree.

    Contains the path from a leaf to the root, enabling verification
    that a specific entry exists in the tree without revealing other entries.

    Attributes:
        leaf_hash: Hash of the leaf being proven
        leaf_index: Index of the leaf in the tree
        proof_hashes: List of (hash, position) tuples where position is "left" or "right"
                     indicating which side the sibling hash is on
        root_hash: Hash of the tree root
        tree_size: Number of leaves in the tree when proof was generated
    """

    leaf_hash: str
    leaf_index: int
    proof_hashes: List[Tuple[str, str]] = field(default_factory=list)
    root_hash: str = ""
    tree_size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize proof to dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return {
            "leaf_hash": self.leaf_hash,
            "leaf_index": self.leaf_index,
            "proof_hashes": [{"hash": h, "position": p} for h, p in self.proof_hashes],
            "root_hash": self.root_hash,
            "tree_size": self.tree_size,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MerkleProof":
        """
        Deserialize proof from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Reconstructed MerkleProof
        """
        proof_hashes = [
            (item["hash"], item["position"]) for item in data.get("proof_hashes", [])
        ]
        return cls(
            leaf_hash=data["leaf_hash"],
            leaf_index=data["leaf_index"],
            proof_hashes=proof_hashes,
            root_hash=data["root_hash"],
            tree_size=data["tree_size"],
        )


class MerkleTree:
    """
    SHA-256 Merkle tree for audit log verification.

    Enables:
    - O(log n) proof generation
    - O(log n) proof verification
    - Tamper detection for individual entries

    The tree is built from a list of leaf hashes. Each internal node
    is the hash of its two children concatenated. If the number of
    leaves is odd, the last leaf is duplicated.

    Example:
        >>> tree = MerkleTree(["hash1", "hash2", "hash3", "hash4"])
        >>> proof = tree.generate_proof(1)  # Proof for second leaf
        >>> tree.verify_proof(proof)
        True

    Attributes:
        _leaves: List of leaf hashes
        _root: Root node of the tree (None if tree is empty)
    """

    def __init__(self, leaves: Optional[List[str]] = None):
        """
        Build tree from leaf hashes.

        Args:
            leaves: List of SHA-256 hex-encoded hashes. If None or empty,
                   creates an empty tree.
        """
        self._leaves: List[str] = list(leaves) if leaves else []
        self._root: Optional[MerkleNode] = None
        if self._leaves:
            self._build()

    def _build(self) -> None:
        """
        Build the Merkle tree from leaves.

        Creates leaf nodes from the hashes, then builds up the tree
        by hashing pairs of nodes together. If there's an odd number
        of nodes at any level, the last node is duplicated.
        """
        if not self._leaves:
            self._root = None
            return

        # Create leaf nodes
        nodes: List[MerkleNode] = [
            MerkleNode(hash=leaf_hash, data_index=i)
            for i, leaf_hash in enumerate(self._leaves)
        ]

        # Build up tree by hashing pairs
        while len(nodes) > 1:
            next_level: List[MerkleNode] = []

            for i in range(0, len(nodes), 2):
                left = nodes[i]

                # Handle odd number of nodes by duplicating the last one
                if i + 1 < len(nodes):
                    right = nodes[i + 1]
                else:
                    right = left

                # Create parent node
                parent_hash = self._hash_pair(left.hash, right.hash)
                parent = MerkleNode(hash=parent_hash, left=left, right=right)
                next_level.append(parent)

            nodes = next_level

        self._root = nodes[0] if nodes else None

    def _hash_pair(self, left: str, right: str) -> str:
        """
        Hash two nodes together.

        Concatenates the two hashes and computes SHA-256.

        Args:
            left: Left node hash
            right: Right node hash

        Returns:
            SHA-256 hash of the concatenation
        """
        combined = (left + right).encode("utf-8")
        return hashlib.sha256(combined).hexdigest()

    @property
    def root_hash(self) -> Optional[str]:
        """
        Get root hash.

        Returns:
            The root hash, or None if tree is empty
        """
        return self._root.hash if self._root else None

    @property
    def leaf_count(self) -> int:
        """
        Number of leaves in the tree.

        Returns:
            Number of leaves
        """
        return len(self._leaves)

    def add_leaf(self, leaf_hash: str) -> None:
        """
        Add a leaf and rebuild tree.

        Note: This invalidates any previously generated proofs.

        Args:
            leaf_hash: SHA-256 hex-encoded hash to add
        """
        self._leaves.append(leaf_hash)
        self._build()

    def get_leaf(self, index: int) -> str:
        """
        Get leaf hash at index.

        Args:
            index: Leaf index

        Returns:
            Leaf hash at the given index

        Raises:
            IndexError: If index is out of range
        """
        if index < 0 or index >= len(self._leaves):
            raise IndexError(
                f"Leaf index {index} out of range [0, {len(self._leaves)})"
            )
        return self._leaves[index]

    def generate_proof(self, index: int) -> Optional[MerkleProof]:
        """
        Generate inclusion proof for leaf at index.

        Walks from the leaf to the root, collecting sibling hashes
        along the way. The proof can be used to verify inclusion
        without access to the full tree.

        Args:
            index: Index of the leaf to generate proof for

        Returns:
            MerkleProof containing the path from leaf to root, or None if tree is empty

        Raises:
            IndexError: If index is out of range

        Note:
            CARE-057: Empty tree handling is consistent with verify_proof().
            Both methods handle empty/None cases gracefully without exceptions:
            - generate_proof() returns None for empty trees
            - verify_proof() returns False for None proofs
            This allows callers to use simple truthiness checks rather than
            try/except blocks for the common case of operating on potentially
            empty trees.
        """
        # CARE-057: Return None for empty trees instead of raising ValueError
        # for consistent behavior with verify_proof() which returns False
        if not self._leaves:
            return None

        if index < 0 or index >= len(self._leaves):
            raise IndexError(
                f"Leaf index {index} out of range [0, {len(self._leaves)})"
            )

        leaf_hash = self._leaves[index]
        proof_hashes: List[Tuple[str, str]] = []

        # Walk up the tree, collecting sibling hashes
        current_index = index
        level_size = len(self._leaves)

        # Build nodes for current level to traverse
        current_level_hashes = list(self._leaves)

        while level_size > 1:
            next_level_hashes: List[str] = []

            # Handle odd level by duplicating last node
            if len(current_level_hashes) % 2 == 1:
                current_level_hashes.append(current_level_hashes[-1])

            for i in range(0, len(current_level_hashes), 2):
                left_hash = current_level_hashes[i]
                right_hash = current_level_hashes[i + 1]
                parent_hash = self._hash_pair(left_hash, right_hash)
                next_level_hashes.append(parent_hash)

            # Find sibling and record it
            if current_index % 2 == 0:
                # Current is left child, sibling is on right
                sibling_index = current_index + 1
                if sibling_index < len(current_level_hashes):
                    sibling_hash = current_level_hashes[sibling_index]
                else:
                    # Duplicated last node
                    sibling_hash = current_level_hashes[current_index]
                proof_hashes.append((sibling_hash, "right"))
            else:
                # Current is right child, sibling is on left
                sibling_index = current_index - 1
                sibling_hash = current_level_hashes[sibling_index]
                proof_hashes.append((sibling_hash, "left"))

            # Move to next level
            current_level_hashes = next_level_hashes
            current_index = current_index // 2
            level_size = len(next_level_hashes)

        return MerkleProof(
            leaf_hash=leaf_hash,
            leaf_index=index,
            proof_hashes=proof_hashes,
            root_hash=self.root_hash or "",
            tree_size=len(self._leaves),
        )

    def verify_proof(self, proof: Optional[MerkleProof]) -> bool:
        """
        Verify a Merkle proof against this tree.

        Recomputes the root hash from the leaf and proof hashes,
        then compares with both the proof's stored root hash AND
        the tree's current root hash. This ensures proofs become
        invalid if the tree has changed since the proof was generated.

        Args:
            proof: The proof to verify, or None

        Returns:
            True if proof is valid AND matches current tree, False otherwise

        Note:
            CARE-057: None proofs are handled gracefully (return False) for
            consistent behavior with generate_proof() which returns None for
            empty trees. This allows chaining like:
                proof = tree.generate_proof(index)
                if tree.verify_proof(proof): ...
        """
        # CARE-057: Handle None proofs gracefully for consistency with
        # generate_proof() returning None for empty trees
        if proof is None:
            return False

        if not self._root:
            return False

        # First verify the proof is internally consistent
        if not verify_merkle_proof(proof.leaf_hash, proof):
            return False

        # Then verify the proof's root matches the tree's current root
        # This catches the case where the tree has been modified since
        # the proof was generated
        return proof.root_hash == self.root_hash

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize tree metadata.

        Does not include full tree structure, just metadata needed
        for verification.

        Returns:
            Dictionary representation
        """
        return {
            "root_hash": self.root_hash,
            "leaf_count": self.leaf_count,
            "leaves": list(self._leaves),
            "version": "1.0",
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MerkleTree":
        """
        Deserialize tree from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Reconstructed MerkleTree
        """
        return cls(leaves=data.get("leaves", []))

    @classmethod
    def from_audit_records(cls, records: List["AuditRecord"]) -> "MerkleTree":
        """
        Build tree from AuditRecord list using integrity_hash.

        Args:
            records: List of AuditRecord instances

        Returns:
            MerkleTree built from the records' integrity hashes
        """
        leaf_hashes = [record.integrity_hash for record in records]
        return cls(leaves=leaf_hashes)


def verify_merkle_proof(leaf_hash: str, proof: MerkleProof) -> bool:
    """
    Verify a Merkle proof without needing the full tree.

    Recomputes the root from the leaf and proof hashes, then
    compares with the proof's root hash.

    Args:
        leaf_hash: Hash of the leaf to verify
        proof: The proof containing sibling hashes and root

    Returns:
        True if the proof is valid (leaf is in tree), False otherwise
    """
    if not proof.root_hash:
        return False

    # Verify the leaf hash matches
    if leaf_hash != proof.leaf_hash:
        return False

    # Recompute root from leaf + proof hashes
    current_hash = leaf_hash

    for sibling_hash, position in proof.proof_hashes:
        if position == "left":
            # Sibling is on the left, combine: sibling + current
            combined = (sibling_hash + current_hash).encode("utf-8")
        else:
            # Sibling is on the right, combine: current + sibling
            combined = (current_hash + sibling_hash).encode("utf-8")

        current_hash = hashlib.sha256(combined).hexdigest()

    # Compare computed root with proof's root hash
    return current_hash == proof.root_hash


def compute_merkle_root(hashes: List[str]) -> Optional[str]:
    """
    Compute Merkle root from a list of hashes without building full tree.

    Utility function for quick root computation.

    Args:
        hashes: List of leaf hashes

    Returns:
        Root hash, or None if list is empty
    """
    if not hashes:
        return None

    tree = MerkleTree(leaves=hashes)
    return tree.root_hash


def get_proof_length(tree_size: int) -> int:
    """
    Calculate the expected proof length for a tree of given size.

    The proof length is ceil(log2(tree_size)) for trees with more
    than one leaf.

    Args:
        tree_size: Number of leaves in the tree

    Returns:
        Expected number of hashes in the proof
    """
    if tree_size <= 1:
        return 0
    return math.ceil(math.log2(tree_size))
