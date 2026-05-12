# -*- coding: utf-8 -*-
"""
gee_project
*DESCRIPTION*

Author: rparker
Created: 2026-04-13
"""

import ee


class GEEProject:

    def __init__(self, project_name):
        self.project_name = project_name
        print(f'Initializing: {self.project_name}')
        ee.Initialize(project=self.project_name)
        return
