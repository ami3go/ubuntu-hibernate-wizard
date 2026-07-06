from ubuntu_hibernate_wizard.core.parsers import SwapDevice
from ubuntu_hibernate_wizard.services.encryption_detector import classify_encryption_for_swap, parse_crypttab
from ubuntu_hibernate_wizard.services.swap_detector import classify_swap_targets

UUID = "d76e67b3-404f-461e-a961-7963664d66b3"
RAM = 8 * 1024**3
BIG = 16 * 1024**3


def test_parse_crypttab_random_key_entry():
    entries, warnings = parse_crypttab(f"cryptswap UUID={UUID} /dev/urandom swap,cipher=aes\n")
    assert not warnings
    assert entries[0].uses_random_key
    assert entries[0].has_swap_option


def test_random_key_encrypted_swap_is_blocked():
    meta = classify_encryption_for_swap(
        "/dev/mapper/cryptswap",
        crypttab_text=f"cryptswap UUID={UUID} /dev/urandom swap,cipher=aes\n",
        uuid=UUID,
    )
    targets = classify_swap_targets(
        [SwapDevice("/dev/mapper/cryptswap", "partition", BIG, 0, -2)],
        RAM,
        {"/dev/mapper/cryptswap": {"uuid": UUID, **meta}},
    )
    assert targets[0].classification == "encrypted_random_key_swap"
    assert targets[0].status == "blocked"
    assert any("random" in r.lower() for r in targets[0].reasons)


def test_unknown_mapper_swap_is_blocked():
    meta = classify_encryption_for_swap("/dev/mapper/swap0", uuid=UUID, dmsetup_info="")
    target = classify_swap_targets(
        [SwapDevice("/dev/mapper/swap0", "partition", BIG, 0, -2)],
        RAM,
        {"/dev/mapper/swap0": {"uuid": UUID, **meta}},
    )[0]
    assert target.classification == "unknown_mapper_swap"
    assert target.status == "blocked"


def test_encrypted_root_plain_swapfile_is_not_misclassified_as_encrypted_block_swap():
    meta = classify_encryption_for_swap(
        "/swap.img",
        uuid=UUID,
        backing_device="/dev/mapper/cryptroot",
        root_source="/dev/mapper/cryptroot",
    )
    target = classify_swap_targets(
        [SwapDevice("/swap.img", "file", BIG, 0, -1)],
        RAM,
        {"/swap.img": {"filesystem": "ext4", "uuid": UUID, "resume_offset": 5986304, **meta}},
    )[0]
    assert target.classification == "swapfile_on_encrypted_root"
    assert not target.encrypted
    assert target.status == "recommended"
