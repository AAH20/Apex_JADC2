"""Tests for coalition federation module (TDD)."""

from __future__ import annotations

import pytest

from src.federation.coalition import (
    ClassificationLevel,
    ClassificationMarking,
    CoalitionPartner,
    CrossDomainGuard,
    DataItem,
    FederationGateway,
    FMNMessage,
    FMNProfile,
    ReleaseabilityMarking,
    SecurityViolation,
)


# ---------------------------------------------------------------------------
# ClassificationLevel
# ---------------------------------------------------------------------------


class TestClassificationLevel:
    def test_ordering(self):
        assert ClassificationLevel.UNCLASSIFIED < ClassificationLevel.RESTRICTED
        assert ClassificationLevel.RESTRICTED < ClassificationLevel.CONFIDENTIAL
        assert ClassificationLevel.CONFIDENTIAL < ClassificationLevel.SECRET
        assert ClassificationLevel.SECRET < ClassificationLevel.TOP_SECRET

    def test_from_string(self):
        assert ClassificationLevel.from_string("UNCLASSIFIED") == ClassificationLevel.UNCLASSIFIED
        assert ClassificationLevel.from_string("secret") == ClassificationLevel.SECRET
        assert ClassificationLevel.from_string("Top_Secret") == ClassificationLevel.TOP_SECRET

    def test_from_string_invalid(self):
        with pytest.raises(ValueError):
            ClassificationLevel.from_string("INVALID")

    def test_numeric_value(self):
        assert ClassificationLevel.UNCLASSIFIED.value == 0
        assert ClassificationLevel.TOP_SECRET.value == 4


# ---------------------------------------------------------------------------
# ReleaseabilityMarking
# ---------------------------------------------------------------------------


class TestReleaseabilityMarking:
    def test_nato_release(self):
        rel = ReleaseabilityMarking(["NATO"])
        assert rel.is_releasable_to("NATO")
        assert not rel.is_releasable_to("FVEY")

    def test_multiple_releasability(self):
        rel = ReleaseabilityMarking(["NATO", "FVEY", "USA"])
        assert rel.is_releasable_to("NATO")
        assert rel.is_releasable_to("FVEY")
        assert rel.is_releasable_to("USA")
        assert not rel.is_releasable_to("GBR")

    def test_no_releasability(self):
        rel = ReleaseabilityMarking([])
        assert not rel.is_releasable_to("NATO")

    def test_default_nato(self):
        rel = ReleaseabilityMarking.nato_default()
        assert rel.is_releasable_to("NATO")
        assert not rel.is_releasable_to("FVEY")


# ---------------------------------------------------------------------------
# ClassificationMarking
# ---------------------------------------------------------------------------


class TestClassificationMarking:
    def test_simple_marking(self):
        marking = ClassificationMarking(
            level=ClassificationLevel.SECRET,
            releaseability=ReleaseabilityMarking(["NATO"]),
        )
        assert marking.level == ClassificationLevel.SECRET
        assert "SECRET" in marking.to_string()
        assert "REL TO NATO" in marking.to_string()

    def test_with_compartments(self):
        marking = ClassificationMarking(
            level=ClassificationLevel.TOP_SECRET,
            releaseability=ReleaseabilityMarking(["FVEY"]),
            compartments={"SI", "TK"},
        )
        s = marking.to_string()
        assert "TOP SECRET" in s
        assert "SI" in s
        assert "TK" in s

    def test_parse_string(self):
        marking = ClassificationMarking.parse("SECRET//REL TO NATO//SI")
        assert marking.level == ClassificationLevel.SECRET
        assert marking.releaseability.is_releasable_to("NATO")
        assert "SI" in marking.compartments

    def test_parse_simple(self):
        marking = ClassificationMarking.parse("UNCLASSIFIED")
        assert marking.level == ClassificationLevel.UNCLASSIFIED
        assert not marking.compartments

    def test_dominates(self):
        secret = ClassificationMarking(
            level=ClassificationLevel.SECRET,
            releaseability=ReleaseabilityMarking(["NATO"]),
        )
        confidential = ClassificationMarking(
            level=ClassificationLevel.CONFIDENTIAL,
            releaseability=ReleaseabilityMarking(["NATO"]),
        )
        assert secret.dominates(confidential)
        assert not confidential.dominates(secret)

    def test_dominates_same_level(self):
        a = ClassificationMarking(
            level=ClassificationLevel.SECRET,
            releaseability=ReleaseabilityMarking(["NATO"]),
        )
        b = ClassificationMarking(
            level=ClassificationLevel.SECRET,
            releaseability=ReleaseabilityMarking(["NATO"]),
        )
        assert a.dominates(b)
        assert b.dominates(a)


# ---------------------------------------------------------------------------
# CoalitionPartner
# ---------------------------------------------------------------------------


class TestCoalitionPartner:
    def test_partner_creation(self):
        partner = CoalitionPartner(
            partner_id="USA",
            name="United States",
            clearance_level=ClassificationLevel.TOP_SECRET,
            releaseability={"NATO", "FVEY", "USA"},
        )
        assert partner.partner_id == "USA"
        assert partner.clearance_level == ClassificationLevel.TOP_SECRET

    def test_can_access(self):
        partner = CoalitionPartner(
            partner_id="GBR",
            name="United Kingdom",
            clearance_level=ClassificationLevel.SECRET,
            releaseability={"NATO", "FVEY"},
        )
        marking = ClassificationMarking(
            level=ClassificationLevel.SECRET,
            releaseability=ReleaseabilityMarking(["NATO"]),
        )
        assert partner.can_access(marking)

    def test_cannot_access_higher_classification(self):
        partner = CoalitionPartner(
            partner_id="FRA",
            name="France",
            clearance_level=ClassificationLevel.CONFIDENTIAL,
            releaseability={"NATO"},
        )
        marking = ClassificationMarking(
            level=ClassificationLevel.SECRET,
            releaseability=ReleaseabilityMarking(["NATO"]),
        )
        assert not partner.can_access(marking)

    def test_cannot_access_wrong_releaseability(self):
        partner = CoalitionPartner(
            partner_id="USA",
            name="United States",
            clearance_level=ClassificationLevel.TOP_SECRET,
            releaseability={"USA", "FVEY"},
        )
        marking = ClassificationMarking(
            level=ClassificationLevel.SECRET,
            releaseability=ReleaseabilityMarking(["NATO"]),
        )
        assert not partner.can_access(marking)

    def test_compartment_access(self):
        partner = CoalitionPartner(
            partner_id="USA",
            name="United States",
            clearance_level=ClassificationLevel.TOP_SECRET,
            releaseability={"NATO", "FVEY", "USA"},
            compartments={"SI", "TK"},
        )
        marking = ClassificationMarking(
            level=ClassificationLevel.TOP_SECRET,
            releaseability=ReleaseabilityMarking(["NATO"]),
            compartments={"SI"},
        )
        assert partner.can_access(marking)

    def test_compartment_denied(self):
        partner = CoalitionPartner(
            partner_id="GBR",
            name="United Kingdom",
            clearance_level=ClassificationLevel.TOP_SECRET,
            releaseability={"NATO", "FVEY"},
            compartments={"SI"},
        )
        marking = ClassificationMarking(
            level=ClassificationLevel.TOP_SECRET,
            releaseability=ReleaseabilityMarking(["NATO"]),
            compartments={"SI", "TK"},
        )
        assert not partner.can_access(marking)


# ---------------------------------------------------------------------------
# DataItem
# ---------------------------------------------------------------------------


class TestDataItem:
    def test_data_item_creation(self):
        item = DataItem(
            item_id="track-001",
            content="Target coordinates",
            marking=ClassificationMarking(
                level=ClassificationLevel.SECRET,
                releaseability=ReleaseabilityMarking(["NATO"]),
            ),
            source_partner="USA",
        )
        assert item.item_id == "track-001"
        assert item.source_partner == "USA"

    def test_data_item_requires_marking(self):
        with pytest.raises(ValueError):
            DataItem(
                item_id="track-002",
                content="test",
                marking=None,
                source_partner="USA",
            )


# ---------------------------------------------------------------------------
# FMNMessage
# ---------------------------------------------------------------------------


class TestFMNMessage:
    def test_fmn_message_creation(self):
        msg = FMNMessage(
            message_id="msg-001",
            sender_id="USA",
            recipient_ids=["GBR", "FRA"],
            profile=FMNProfile.FMN_SPIRAL_4,
            payload={"type": "track", "data": "coords"},
            marking=ClassificationMarking(
                level=ClassificationLevel.SECRET,
                releaseability=ReleaseabilityMarking(["NATO"]),
            ),
        )
        assert msg.message_id == "msg-001"
        assert msg.sender_id == "USA"
        assert "GBR" in msg.recipient_ids

    def test_fmn_message_serialization(self):
        msg = FMNMessage(
            message_id="msg-002",
            sender_id="USA",
            recipient_ids=["NATO"],
            profile=FMNProfile.FMN_SPIRAL_4,
            payload={"type": "status"},
            marking=ClassificationMarking(
                level=ClassificationLevel.RESTRICTED,
                releaseability=ReleaseabilityMarking(["NATO"]),
            ),
        )
        serialized = msg.to_dict()
        assert serialized["message_id"] == "msg-002"
        assert serialized["sender_id"] == "USA"
        assert serialized["profile"] == "FMN_SPIRAL_4"

    def test_fmn_profile_values(self):
        assert FMNProfile.FMN_SPIRAL_1.value == "FMN_SPIRAL_1"
        assert FMNProfile.FMN_SPIRAL_4.value == "FMN_SPIRAL_4"
        assert FMNProfile.FMN_SPIRAL_5.value == "FMN_SPIRAL_5"


# ---------------------------------------------------------------------------
# CrossDomainGuard
# ---------------------------------------------------------------------------


class TestCrossDomainGuard:
    def test_same_domain_transfer(self):
        guard = CrossDomainGuard()
        marking = ClassificationMarking(
            level=ClassificationLevel.SECRET,
            releaseability=ReleaseabilityMarking(["NATO"]),
        )
        # Same domain should always succeed
        assert guard.check_transfer(marking, ClassificationLevel.SECRET)

    def test_downgrade_transfer(self):
        guard = CrossDomainGuard()
        marking = ClassificationMarking(
            level=ClassificationLevel.CONFIDENTIAL,
            releaseability=ReleaseabilityMarking(["NATO"]),
        )
        # Downgrade (to lower classification) should succeed
        assert guard.check_transfer(marking, ClassificationLevel.RESTRICTED)

    def test_upgrade_transfer_blocked(self):
        guard = CrossDomainGuard()
        marking = ClassificationMarking(
            level=ClassificationLevel.SECRET,
            releaseability=ReleaseabilityMarking(["NATO"]),
        )
        # Upgrade should be blocked
        assert not guard.check_transfer(marking, ClassificationLevel.TOP_SECRET)

    def test_guard_audit_trail(self):
        guard = CrossDomainGuard()
        marking = ClassificationMarking(
            level=ClassificationLevel.SECRET,
            releaseability=ReleaseabilityMarking(["NATO"]),
        )
        guard.check_transfer(marking, ClassificationLevel.TOP_SECRET)
        trail = guard.get_audit_trail()
        assert len(trail) == 1
        assert trail[0].action == "blocked"


# ---------------------------------------------------------------------------
# FederationGateway
# ---------------------------------------------------------------------------


class TestFederationGateway:
    def test_register_partner(self):
        gw = FederationGateway()
        partner = CoalitionPartner(
            partner_id="USA",
            name="United States",
            clearance_level=ClassificationLevel.TOP_SECRET,
            releaseability={"NATO", "FVEY", "USA"},
        )
        gw.register_partner(partner)
        assert gw.get_partner("USA") is partner

    def test_share_data(self):
        gw = FederationGateway()
        usa = CoalitionPartner(
            partner_id="USA",
            name="United States",
            clearance_level=ClassificationLevel.TOP_SECRET,
            releaseability={"NATO", "FVEY", "USA"},
        )
        gbr = CoalitionPartner(
            partner_id="GBR",
            name="United Kingdom",
            clearance_level=ClassificationLevel.SECRET,
            releaseability={"NATO", "FVEY"},
        )
        gw.register_partner(usa)
        gw.register_partner(gbr)

        item = DataItem(
            item_id="track-001",
            content="Shared track data",
            marking=ClassificationMarking(
                level=ClassificationLevel.SECRET,
                releaseability=ReleaseabilityMarking(["NATO"]),
            ),
            source_partner="USA",
        )
        gw.share_data(item, "USA", ["GBR"])
        # GBR has SECRET clearance and NATO releaseability — should succeed
        shared = gw.get_shared_data("GBR")
        assert any(d.item_id == "track-001" for d in shared)

    def test_share_data_denied(self):
        gw = FederationGateway()
        usa = CoalitionPartner(
            partner_id="USA",
            name="United States",
            clearance_level=ClassificationLevel.TOP_SECRET,
            releaseability={"NATO", "FVEY", "USA"},
        )
        fra = CoalitionPartner(
            partner_id="FRA",
            name="France",
            clearance_level=ClassificationLevel.CONFIDENTIAL,
            releaseability={"NATO"},
        )
        gw.register_partner(usa)
        gw.register_partner(fra)

        item = DataItem(
            item_id="track-002",
            content="Secret data",
            marking=ClassificationMarking(
                level=ClassificationLevel.SECRET,
                releaseability=ReleaseabilityMarking(["NATO"]),
            ),
            source_partner="USA",
        )
        with pytest.raises(SecurityViolation):
            gw.share_data(item, "USA", ["FRA"])

    def test_send_fmn_message(self):
        gw = FederationGateway()
        usa = CoalitionPartner(
            partner_id="USA",
            name="United States",
            clearance_level=ClassificationLevel.TOP_SECRET,
            releaseability={"NATO", "FVEY", "USA"},
        )
        gbr = CoalitionPartner(
            partner_id="GBR",
            name="United Kingdom",
            clearance_level=ClassificationLevel.SECRET,
            releaseability={"NATO", "FVEY"},
        )
        gw.register_partner(usa)
        gw.register_partner(gbr)

        msg = FMNMessage(
            message_id="msg-003",
            sender_id="USA",
            recipient_ids=["GBR"],
            profile=FMNProfile.FMN_SPIRAL_4,
            payload={"type": "track"},
            marking=ClassificationMarking(
                level=ClassificationLevel.SECRET,
                releaseability=ReleaseabilityMarking(["NATO"]),
            ),
        )
        gw.send_fmn_message(msg)
        messages = gw.get_messages_for_partner("GBR")
        assert any(m.message_id == "msg-003" for m in messages)

    def test_send_fmn_message_denied(self):
        gw = FederationGateway()
        usa = CoalitionPartner(
            partner_id="USA",
            name="United States",
            clearance_level=ClassificationLevel.TOP_SECRET,
            releaseability={"NATO", "FVEY", "USA"},
        )
        fra = CoalitionPartner(
            partner_id="FRA",
            name="France",
            clearance_level=ClassificationLevel.CONFIDENTIAL,
            releaseability={"NATO"},
        )
        gw.register_partner(usa)
        gw.register_partner(fra)

        msg = FMNMessage(
            message_id="msg-004",
            sender_id="USA",
            recipient_ids=["FRA"],
            profile=FMNProfile.FMN_SPIRAL_4,
            payload={"type": "track"},
            marking=ClassificationMarking(
                level=ClassificationLevel.SECRET,
                releaseability=ReleaseabilityMarking(["NATO"]),
            ),
        )
        with pytest.raises(SecurityViolation):
            gw.send_fmn_message(msg)

    def test_get_shared_data_isolation(self):
        gw = FederationGateway()
        usa = CoalitionPartner(
            partner_id="USA",
            name="United States",
            clearance_level=ClassificationLevel.TOP_SECRET,
            releaseability={"NATO", "FVEY", "USA"},
        )
        gbr = CoalitionPartner(
            partner_id="GBR",
            name="United Kingdom",
            clearance_level=ClassificationLevel.SECRET,
            releaseability={"NATO", "FVEY"},
        )
        gw.register_partner(usa)
        gw.register_partner(gbr)

        item = DataItem(
            item_id="track-003",
            content="NATO secret",
            marking=ClassificationMarking(
                level=ClassificationLevel.SECRET,
                releaseability=ReleaseabilityMarking(["NATO"]),
            ),
            source_partner="USA",
        )
        gw.share_data(item, "USA", ["GBR"])

        # GBR should see it
        gbr_data = gw.get_shared_data("GBR")
        assert any(d.item_id == "track-003" for d in gbr_data)

        # USA should also see it (as source)
        usa_data = gw.get_shared_data("USA")
        assert any(d.item_id == "track-003" for d in usa_data)

    def test_duplicate_partner_registration(self):
        gw = FederationGateway()
        partner = CoalitionPartner(
            partner_id="USA",
            name="United States",
            clearance_level=ClassificationLevel.TOP_SECRET,
            releaseability={"NATO"},
        )
        gw.register_partner(partner)
        with pytest.raises(ValueError):
            gw.register_partner(partner)

    def test_unknown_partner(self):
        gw = FederationGateway()
        with pytest.raises(ValueError):
            gw.get_partner("XXX")

    def test_audit_trail(self):
        gw = FederationGateway()
        usa = CoalitionPartner(
            partner_id="USA",
            name="United States",
            clearance_level=ClassificationLevel.TOP_SECRET,
            releaseability={"NATO", "FVEY", "USA"},
        )
        gw.register_partner(usa)

        item = DataItem(
            item_id="track-004",
            content="data",
            marking=ClassificationMarking(
                level=ClassificationLevel.SECRET,
                releaseability=ReleaseabilityMarking(["NATO"]),
            ),
            source_partner="USA",
        )
        gw.share_data(item, "USA", ["USA"])
        trail = gw.get_audit_trail()
        assert len(trail) >= 1
