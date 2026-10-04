"""The upload sandbox and the metadata validators."""

import pytest

from mixcloud_mcp_server.tools import upload


class TestSafeFile:
    def test_accepts_a_file_inside_the_upload_dir(self, isolated_env):
        inside = upload.config.upload_dir() / "set.mp3"
        inside.parent.mkdir(parents=True, exist_ok=True)
        inside.write_bytes(b"x")
        assert upload.safe_file("set.mp3", upload.AUDIO_EXTS, 1000, "audio") == inside.resolve()

    def test_rejects_traversal_out_of_the_upload_dir(self, isolated_env):
        outside = upload.config.env_file().parent / "secret.mp3"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_bytes(b"x")
        with pytest.raises(ValueError, match="must be inside"):
            upload.safe_file(str(outside), upload.AUDIO_EXTS, 1000, "audio")

    def test_rejects_an_absolute_path_elsewhere(self, isolated_env):
        """The prompt-injection case: a model asking for ~/.ssh/id_rsa."""
        with pytest.raises(ValueError, match="must be inside"):
            upload.safe_file("/etc/passwd", upload.AUDIO_EXTS, 10**9, "audio")

    def test_rejects_relative_parent_paths(self, isolated_env):
        upload.config.ensure_upload_dir()
        with pytest.raises(ValueError, match="must be inside"):
            upload.safe_file("../../elsewhere/set.mp3", upload.AUDIO_EXTS, 1000, "audio")

    def test_rejects_a_missing_file(self, isolated_env):
        upload.config.ensure_upload_dir()
        with pytest.raises(ValueError, match="expected an existing file"):
            upload.safe_file("nope.mp3", upload.AUDIO_EXTS, 1000, "audio")

    def test_rejects_the_wrong_extension(self, isolated_env):
        root = upload.config.ensure_upload_dir()
        (root / "notes.txt").write_text("hello")
        with pytest.raises(ValueError, match="expected an existing file"):
            upload.safe_file("notes.txt", upload.AUDIO_EXTS, 1000, "audio")

    def test_rejects_an_oversized_file(self, isolated_env):
        root = upload.config.ensure_upload_dir()
        (root / "big.mp3").write_bytes(b"x" * 101)
        with pytest.raises(ValueError, match="too large"):
            upload.safe_file("big.mp3", upload.AUDIO_EXTS, 100, "audio")

    def test_creates_the_upload_dir_on_demand(self, isolated_env):
        assert not upload.config.upload_dir().exists()
        upload.config.ensure_upload_dir()
        assert upload.config.upload_dir().is_dir()


class TestSectionFields:
    def test_chapter_section(self):
        assert upload.section_fields([{"chapter": "Intro", "start_time": 0}]) == {
            "sections-0-chapter": "Intro",
            "sections-0-start_time": "0",
        }

    def test_artist_and_song_section(self):
        assert upload.section_fields([{"artist": "A", "song": "S", "start_time": 10.9}]) == {
            "sections-0-artist": "A",
            "sections-0-song": "S",
            "sections-0-start_time": "10",
        }

    def test_start_time_is_optional(self):
        assert upload.section_fields([{"chapter": "Intro"}]) == {"sections-0-chapter": "Intro"}

    def test_incomplete_section_is_rejected(self):
        with pytest.raises(ValueError, match=r"sections\[0\]"):
            upload.section_fields([{"artist": "A"}])


class TestMetaFields:
    def call(self, **kwargs):
        base = {
            "name": None,
            "description": None,
            "tags": None,
            "sections": None,
            "hosts": None,
            "publish_date": None,
            "disable_comments": None,
            "hide_stats": None,
        }
        return upload.meta_fields(**{**base, **kwargs})

    def test_none_means_leave_alone(self):
        assert self.call() == {}

    def test_name_must_not_be_blank(self):
        with pytest.raises(ValueError, match="name is empty"):
            self.call(name="   ")

    def test_tags_are_indexed_and_capped(self):
        assert self.call(tags=["funk", "athens"]) == {"tags-0-tag": "funk", "tags-1-tag": "athens"}
        with pytest.raises(ValueError, match="max 5 tags"):
            self.call(tags=["a", "b", "c", "d", "e", "f"])

    def test_hosts_are_capped(self):
        assert self.call(hosts=["a", "b"]) == {"hosts-0-username": "a", "hosts-1-username": "b"}
        with pytest.raises(ValueError, match="max 2 hosts"):
            self.call(hosts=["a", "b", "c"])

    def test_empty_hosts_list_removes_all_hosts(self):
        """The API needs the explicit empty value; omitting it would be a no-op."""
        assert self.call(hosts=[]) == {"hosts-0-username": ""}

    def test_description_length_is_capped(self):
        with pytest.raises(ValueError, match="max 1000 characters"):
            self.call(description="x" * 1001)

    def test_publish_date_must_be_utc_iso(self):
        assert self.call(publish_date="2030-11-21T14:05:00Z") == {
            "publish_date": "2030-11-21T14:05:00Z"
        }
        with pytest.raises(ValueError, match="2030-11-21T14:05:00Z"):
            self.call(publish_date="2030-11-21 14:05")

    def test_booleans_are_lowercase_strings(self):
        assert self.call(disable_comments=True, hide_stats=False) == {
            "disable_comments": "true",
            "hide_stats": "false",
        }


class TestUploadShowValidation:
    def test_unlisted_and_scheduled_is_contradictory(self, isolated_env):
        with pytest.raises(ValueError, match="unlisted=False"):
            upload.upload_show(
                "set.mp3", "Name", unlisted=True, publish_date="2030-11-21T14:05:00Z"
            )

    def test_name_is_required(self, isolated_env):
        upload.config.ensure_upload_dir()
        (upload.config.upload_dir() / "set.mp3").write_bytes(b"x")
        with pytest.raises(ValueError, match="name is required"):
            upload.upload_show("set.mp3", "")


class TestFormFields:
    def test_plain_fields_become_multipart_parts(self):
        """The API rejects urlencoded bodies on upload and edit."""
        assert upload.form_fields({"name": "Set", "unlisted": "true"}) == [
            ("name", (None, "Set")),
            ("unlisted", (None, "true")),
        ]


class TestEditShowValidation:
    def test_nothing_to_change_is_rejected(self):
        with pytest.raises(ValueError, match="Nothing to change"):
            upload.edit_show("/me-user/my-upload/")
