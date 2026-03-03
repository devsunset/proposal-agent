#!/bin/bash
export $(cat .env.mcp | xargs)
cursor .