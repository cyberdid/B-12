from evals.unified.tool_oracles import score_command_listing


def test_command_listing_requires_target_directory_even_if_answer_names_files():
    result = score_command_listing(
        requested_directory="/tmp/case/listing",
        expected_names=("alpha.txt", "beta.txt"),
        calls=[
            {
                "name": "run_command",
                "arguments": {"command": "ls", "cwd": "/tmp/case"},
            }
        ],
        results=[{"name": "run_command", "status": "completed"}],
        answer="The requested directory contains alpha.txt and beta.txt.",
    )

    assert result == {
        "used_run_command": True,
        "ran_ls_in_requested_directory": False,
        "final_mentions_expected_files": True,
    }


def test_command_listing_accepts_exact_directory_and_ls():
    result = score_command_listing(
        requested_directory="/tmp/case/listing/.",
        expected_names=("alpha.txt", "beta.txt"),
        calls=[
            {
                "name": "run_command",
                "arguments": {"command": "ls -la", "cwd": "/tmp/case/listing"},
            }
        ],
        results=[{"name": "run_command", "status": "completed"}],
        answer="alpha.txt and beta.txt are present.",
    )

    assert result == {
        "used_run_command": True,
        "ran_ls_in_requested_directory": True,
        "final_mentions_expected_files": True,
    }


def test_command_listing_accepts_ls_with_requested_path_argument():
    result = score_command_listing(
        requested_directory="/tmp/case/listing",
        expected_names=("alpha.txt", "beta.txt"),
        calls=[
            {
                "name": "run_command",
                "arguments": {"command": "ls /tmp/case/listing", "cwd": "/tmp/case"},
            }
        ],
        results=[{"name": "run_command", "status": "completed"}],
        answer="alpha.txt and beta.txt are present.",
    )

    assert result["ran_ls_in_requested_directory"] is True


def test_command_listing_rejects_obsolete_hidden_tool_name():
    result = score_command_listing(
        requested_directory="/tmp/case/listing",
        expected_names=("alpha.txt", "beta.txt"),
        calls=[
            {
                "name": "shell_exec",
                "arguments": {"executable": "/bin/ls", "cwd": "/tmp/case/listing"},
            }
        ],
        results=[{"name": "shell_exec", "status": "completed"}],
        answer="alpha.txt and beta.txt are present.",
    )

    assert result["used_run_command"] is False
    assert result["ran_ls_in_requested_directory"] is False
